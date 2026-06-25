"""
OCR pipeline Celery tasks — queue: ocr

Chain: run_ocr → route_doc → extract_*
"""
import logging
from datetime import datetime, timezone
from celery import shared_task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.engines.pii_masker import mask_pii

logger = logging.getLogger(__name__)


def _pipeline_event(db: Session, doc, stage: str, status: str, error_type: str | None = None, payload: dict | None = None):
    from app.models.document import DocumentPipelineEvent

    db.add(DocumentPipelineEvent(
        org_id=doc.org_id,
        client_id=doc.client_id,
        document_id=doc.id,
        stage=stage,
        status=status,
        error_type=error_type,
        diagnostic_payload=payload or {},
    ))


def _num(value) -> float:
    try:
        cleaned = str(value or "0").replace(",", "").replace("₹", "").strip()
        return float(cleaned or 0)
    except (TypeError, ValueError):
        return 0.0


def _extraction_from_kvs(kvs: dict) -> dict:
    return {
        "supplier_name": kvs.get("VendorName") or kvs.get("SupplierName"),
        "supplier_gstin": kvs.get("VendorTaxId") or kvs.get("CustomerTaxId"),
        "invoice_number": kvs.get("InvoiceId"),
        "invoice_date": kvs.get("InvoiceDate"),
        "taxable_value": _num(kvs.get("SubTotal") or kvs.get("TaxableValue")),
        "cgst_amount": _num(kvs.get("CGST")),
        "sgst_amount": _num(kvs.get("SGST")),
        "igst_amount": _num(kvs.get("IGST")),
        "total_amount": _num(kvs.get("InvoiceTotal")),
        "confidence_score": _num(kvs.get("Confidence") or 1),
        "raw_tax_amount": _num(kvs.get("TotalTax")),
    }


def _validate_extraction(extracted: dict) -> list[dict]:
    errors = []
    if float(extracted.get("confidence_score") or 0) < 0.9:
        errors.append({"code": "LOW_AI_MODEL_CONFIDENCE", "confidence": extracted.get("confidence_score")})
    taxable = float(extracted.get("taxable_value") or 0)
    tax_parts = sum(float(extracted.get(key) or 0) for key in ("cgst_amount", "sgst_amount", "igst_amount"))
    total = float(extracted.get("total_amount") or 0)
    raw_tax = float(extracted.get("raw_tax_amount") or 0)
    if taxable and total and abs(total - (taxable + tax_parts)) > 0.05 and abs(total - (taxable + raw_tax)) > 0.05:
        errors.append({"code": "MATHEMATICAL_MISALIGNMENT", "expected_total": round(taxable + tax_parts, 2), "stated_total": total})
    return errors


def _auto_tags(extracted: dict) -> list[str]:
    text = " ".join(str(extracted.get(key) or "") for key in ("supplier_name", "invoice_number")).lower()
    if any(word in text for word in ("bsnl", "airtel", "jio", "telecom", "internet")):
        return ["expense:telecommunication"]
    if any(word in text for word in ("fuel", "petrol", "diesel")):
        return ["expense:travel"]
    if any(word in text for word in ("rent", "lease")):
        return ["expense:rent"]
    return ["review:uncategorized"]


def _store_extraction(db: Session, doc, extracted: dict, validation_errors: list[dict]) -> str:
    from app.models.document import DocumentExtraction

    validation_status = "failed_validation" if validation_errors else "verified"
    db.add(DocumentExtraction(
        org_id=doc.org_id,
        client_id=doc.client_id,
        document_id=doc.id,
        supplier_name=extracted.get("supplier_name"),
        supplier_gstin=extracted.get("supplier_gstin"),
        invoice_number=extracted.get("invoice_number"),
        invoice_date=str(extracted.get("invoice_date") or "") or None,
        taxable_value=str(extracted.get("taxable_value") or ""),
        cgst_amount=str(extracted.get("cgst_amount") or ""),
        sgst_amount=str(extracted.get("sgst_amount") or ""),
        igst_amount=str(extracted.get("igst_amount") or ""),
        total_amount=str(extracted.get("total_amount") or ""),
        confidence_score=str(extracted.get("confidence_score") or ""),
        validation_status=validation_status,
        validation_errors=validation_errors,
        auto_tags=_auto_tags(extracted),
        raw_extracted_json=extracted,
    ))
    return validation_status


def _mask_nested(value):
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {key: _mask_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_nested(item) for item in value]
    return value


def _get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


@celery_app.task(bind=True, queue="ocr", max_retries=3,
                 autoretry_for=(Exception,), retry_backoff=True)
def run_ocr(self, document_id: str):
    """Process a document through Azure Document Intelligence."""
    from app.models.document import Document
    from app.config import settings

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return
        if doc.status in {"processing", "processed", "verified"}:
            return
        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.last_pipeline_error_type = None
        _pipeline_event(db, doc, "ingestion", "processing")
        db.commit()

        # Structured CSV/JSON documents must be parsed from their original bytes.
        if doc.doc_type in ("purchase_register", "gstr2b"):
            from app.services.s3_service import download_bytes

            raw_text = download_bytes(doc.s3_key).decode("utf-8-sig")
            tables, kvs = [], {}
        else:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
            from app.services.s3_service import get_s3_url

            if not settings.AZURE_DOC_ENDPOINT or not settings.AZURE_DOC_KEY:
                raw_text = f"Local development OCR placeholder for {doc.original_filename or doc.s3_key}"
                tables = []
                kvs = {
                    "VendorName": "Demo Supplier",
                    "InvoiceId": f"DEV-{str(doc.id)[:8]}",
                    "InvoiceTotal": "1000",
                    "SubTotal": "1000",
                    "TotalTax": "0",
                    "Confidence": "0.98",
                }
                _pipeline_event(db, doc, "ai_extraction", "local_fallback", payload={"reason": "azure_not_configured"})
                db.commit()
            else:
                try:
                    client = DocumentIntelligenceClient(
                        endpoint=settings.AZURE_DOC_ENDPOINT,
                        credential=AzureKeyCredential(settings.AZURE_DOC_KEY),
                    )
                    s3_url = get_s3_url(doc.s3_key)
                    poller = client.begin_analyze_document("prebuilt-invoice", {"urlSource": s3_url})
                    result = poller.result()

                    raw_text = result.content or ""
                    tables = []
                    for tbl in (result.tables or []):
                        rows = {}
                        for cell in tbl.cells:
                            rows.setdefault(cell.row_index, {})[cell.column_index] = cell.content
                        tables.append(rows)

                    kvs = {}
                    for doc_result in (result.documents or []):
                        for key, field in (doc_result.fields or {}).items():
                            kvs[key] = field.content if field else None
                    _pipeline_event(db, doc, "ai_extraction", "complete")
                except Exception as e:
                    logger.error(f"Azure OCR failed for document {document_id}: {e}")
                    doc.status = "ocr_failed"
                    doc.last_pipeline_error_type = "AI_INFRASTRUCTURE_CRASH"
                    _pipeline_event(db, doc, "ai_extraction", "failed", "AI_INFRASTRUCTURE_CRASH", {"detail": str(e)})
                    db.commit()
                    raise

        try:
            doc.ocr_text = mask_pii(raw_text)
            doc.ocr_json = {"tables": _mask_nested(tables), "kvs": _mask_nested(kvs)}
            doc.status = "ocr_complete"
            _pipeline_event(db, doc, "ocr", "complete")
            db.commit()
        except Exception as e:
            logger.error(f"Azure OCR failed for document {document_id}: {e}")
            doc.status = "ocr_failed"
            doc.last_pipeline_error_type = "OCR_PERSISTENCE_FAILED"
            _pipeline_event(db, doc, "ocr", "failed", "OCR_PERSISTENCE_FAILED", {"detail": str(e)})
            db.commit()
            raise

        # Chain to document routing
        route_doc.delay(document_id)

    except Exception:
        db.rollback()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "ocr_failed"
            doc.last_pipeline_error_type = "OCR_PIPELINE_FAILED"
            _pipeline_event(db, doc, "pipeline", "failed", "OCR_PIPELINE_FAILED")
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(queue="ocr")
def route_doc(document_id: str):
    """Route a completed OCR document to the appropriate extractor."""
    from app.models.document import Document

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or doc.status != "ocr_complete":
            return

        routing = {
            "invoice":           extract_invoice_transactions,
            "purchase_register": extract_csv_transactions,
            "gstr2b":            extract_gstr2b,
            "bank_statement":    extract_bank_transactions,
        }
        if doc.doc_type == "udyam_certificate":
            from app.tasks.extension_tasks import process_udyam_certificate
            process_udyam_certificate.delay(document_id)
            return
        task_fn = routing.get(doc.doc_type)
        if task_fn:
            task_fn.delay(document_id)
        else:
            doc.status = "verified"
            doc.processing_completed_at = datetime.now(timezone.utc)
            _pipeline_event(db, doc, "routing", "verified")
            db.commit()
        # notice and trial_balance are not auto-extracted — ready for AI modules
    finally:
        db.close()


@celery_app.task(queue="ocr")
def extract_invoice_transactions(document_id: str):
    """Extract Transaction records from an invoice OCR result."""
    from app.models.document import Document
    from app.models.transaction import Transaction
    from app.engines.invoice_fraud_scanner import generate_fingerprint
    import decimal

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.ocr_json:
            return

        kvs = doc.ocr_json.get("kvs", {})

        def _d(val):
            try:
                return float(str(val).replace(",", "").replace("₹", "").strip())
            except (TypeError, ValueError):
                return None

        invoice_data = {
            "vendor_name":  kvs.get("VendorName"),
            "vendor_gstin": kvs.get("CustomerTaxId") or kvs.get("VendorTaxId"),
            "invoice_no":   kvs.get("InvoiceId"),
            "amount":       _d(kvs.get("InvoiceTotal")),
            "tax_amount":   _d(kvs.get("TotalTax")),
            "date":         kvs.get("InvoiceDate"),
        }
        extracted = _extraction_from_kvs(kvs)
        validation_errors = _validate_extraction(extracted)
        validation_status = _store_extraction(db, doc, extracted, validation_errors)
        if validation_errors:
            doc.status = "failed_validation"
            doc.last_pipeline_error_type = validation_errors[0]["code"]
            _pipeline_event(db, doc, "validation", "failed", validation_errors[0]["code"], {"errors": validation_errors})
            db.commit()
            return

        fingerprint = generate_fingerprint({
            "vendor_gstin": invoice_data.get("vendor_gstin", ""),
            "invoice_no":   invoice_data.get("invoice_no", ""),
            "amount":       str(invoice_data.get("amount", "")),
            "date":         str(invoice_data.get("date", "")),
        })

        txn = Transaction(
            org_id=doc.org_id,
            client_id=doc.client_id,
            document_id=doc.id,
            source="upload",
            fingerprint=fingerprint,
            **{k: v for k, v in invoice_data.items() if v is not None},
        )
        db.add(txn)
        doc.status = "processed"
        doc.processing_completed_at = datetime.now(timezone.utc)
        _pipeline_event(db, doc, "schema_ingestion", "processed", payload={"validation_status": validation_status})
        db.commit()
        from app.tasks.anomaly_tasks import run_anomaly_detection, run_invoice_fraud_scan
        run_invoice_fraud_scan.delay(str(txn.id))
        run_anomaly_detection.delay(str(doc.client_id))
    except Exception as e:
        logger.error(f"extract_invoice_transactions failed for {document_id}: {e}")
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "parse_failed"
            doc.last_pipeline_error_type = "INVOICE_EXTRACTION_FAILED"
            _pipeline_event(db, doc, "schema_ingestion", "failed", "INVOICE_EXTRACTION_FAILED", {"detail": str(e)})
            db.commit()
    finally:
        db.close()


@celery_app.task(queue="ocr")
def extract_csv_transactions(document_id: str):
    """Extract Transaction records from a Tally CSV document."""
    import io
    import pandas as pd
    from app.models.document import Document
    from app.models.transaction import Transaction
    from app.engines.tally_normalizer import normalize_tally
    from app.engines.invoice_fraud_scanner import generate_fingerprint

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.ocr_text:
            return

        df = pd.read_csv(io.StringIO(doc.ocr_text))
        df = normalize_tally(df)

        for _, row in df.iterrows():
            fp = generate_fingerprint({
                "vendor_gstin": str(row.get("vendor_gstin", "")),
                "invoice_no":   str(row.get("invoice_no", "")),
                "amount":       str(row.get("amount", "")),
                "date":         str(row.get("date", "")),
            })
            txn = Transaction(
                org_id=doc.org_id,
                client_id=doc.client_id,
                document_id=doc.id,
                source="upload",
                invoice_no=str(row.get("invoice_no", "")) or None,
                vendor_gstin=str(row.get("vendor_gstin", "")) or None,
                vendor_name=str(row.get("vendor_name", "")) or None,
                amount=row.get("amount"),
                date=row.get("date").date() if pd.notna(row.get("date")) else None,
                fingerprint=fp,
            )
            db.add(txn)

        doc.status = "processed"
        doc.processing_completed_at = datetime.now(timezone.utc)
        _pipeline_event(db, doc, "schema_ingestion", "processed")
        db.commit()
    except Exception as e:
        logger.error(f"extract_csv_transactions failed for {document_id}: {e}")
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "parse_failed"
            doc.last_pipeline_error_type = "CSV_EXTRACTION_FAILED"
            _pipeline_event(db, doc, "schema_ingestion", "failed", "CSV_EXTRACTION_FAILED", {"detail": str(e)})
            db.commit()
    finally:
        db.close()


@celery_app.task(queue="ocr")
def extract_gstr2b(document_id: str):
    """Extract Transaction records from a GSTR-2B JSON document."""
    import json
    from app.models.document import Document
    from app.models.transaction import Transaction

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.ocr_text:
            return

        try:
            data = json.loads(doc.ocr_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"GSTR-2B JSON parse failed: {e}")

        # GSTR-2B structure: data.data.docdata.b2b[].inv[]
        b2b_entries = (data.get("data", {}).get("docdata", {}).get("b2b") or [])
        for supplier in b2b_entries:
            gstin = supplier.get("ctin")
            for inv in supplier.get("inv", []):
                txn = Transaction(
                    org_id=doc.org_id,
                    client_id=doc.client_id,
                    document_id=doc.id,
                    source="gstr2b",
                    vendor_gstin=gstin,
                    invoice_no=inv.get("inum"),
                    amount=inv.get("val"),
                    tax_amount=inv.get("igst") or (
                        (inv.get("cgst") or 0) + (inv.get("sgst") or 0)),
                )
                db.add(txn)

        doc.status = "processed"
        doc.processing_completed_at = datetime.now(timezone.utc)
        _pipeline_event(db, doc, "schema_ingestion", "processed")
        db.commit()
    except Exception as e:
        logger.error(f"extract_gstr2b failed for {document_id}: {e}")
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "parse_failed"
            doc.last_pipeline_error_type = "GSTR2B_EXTRACTION_FAILED"
            _pipeline_event(db, doc, "schema_ingestion", "failed", "GSTR2B_EXTRACTION_FAILED", {"detail": str(e)})
            db.commit()
    finally:
        db.close()


@celery_app.task(queue="ocr")
def extract_bank_transactions(document_id: str):
    """Extract basic bank statement transactions from OCR text."""
    from app.models.document import Document

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return
        # Bank statement parsing is document-specific;
        # mark as processed and let the CA review OCR text manually.
        doc.status = "processed"
        doc.processing_completed_at = datetime.now(timezone.utc)
        _pipeline_event(db, doc, "schema_ingestion", "processed")
        db.commit()
    finally:
        db.close()
