import PasswordReset, { subject as sPasswordReset } from './password_reset';
import EmailVerification, { subject as sEmailVerification } from './email_verification';
import UserInvitation, { subject as sUserInvitation } from './user_invitation';
import InvoiceSent, { subject as sInvoiceSent } from './invoice_sent';
import PaymentReceived, { subject as sPaymentReceived } from './payment_received';
import InvoiceOverdue, { subject as sInvoiceOverdue } from './invoice_overdue';
import SubscriptionActivated, { subject as sSubscriptionActivated } from './subscription_activated';
import SubscriptionCancelled, { subject as sSubscriptionCancelled } from './subscription_cancelled';
import SubscriptionHalted, { subject as sSubscriptionHalted } from './subscription_halted';
import DocumentRequest, { subject as sDocumentRequest } from './document_request';
import ReportReady, { subject as sReportReady } from './report_ready';
import PortalInvite, { subject as sPortalInvite } from './portal_invite';

type TemplateEntry = {
  component: React.ComponentType<any>;
  subject: (props: any) => string;
};

export const TEMPLATES: Record<string, TemplateEntry> = {
  password_reset: { component: PasswordReset, subject: sPasswordReset },
  email_verification: { component: EmailVerification, subject: sEmailVerification },
  user_invitation: { component: UserInvitation, subject: sUserInvitation },
  invoice_sent: { component: InvoiceSent, subject: sInvoiceSent },
  payment_received: { component: PaymentReceived, subject: sPaymentReceived },
  invoice_overdue: { component: InvoiceOverdue, subject: sInvoiceOverdue },
  subscription_activated: { component: SubscriptionActivated, subject: sSubscriptionActivated },
  subscription_cancelled: { component: SubscriptionCancelled, subject: sSubscriptionCancelled },
  subscription_halted: { component: SubscriptionHalted, subject: sSubscriptionHalted },
  document_request: { component: DocumentRequest, subject: sDocumentRequest },
  report_ready: { component: ReportReady, subject: sReportReady },
  portal_invite: { component: PortalInvite, subject: sPortalInvite },
};

export const TEMPLATE_KEYS = Object.keys(TEMPLATES);
