import { NextRequest, NextResponse } from 'next/server';
import * as React from 'react';
import { render } from '@react-email/render';
import { TEMPLATES, TEMPLATE_KEYS } from '@/emails';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json({
    templates: TEMPLATE_KEYS,
    count: TEMPLATE_KEYS.length,
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const template = String(body?.template || '').trim();
    const props = body?.props || {};

    if (!template || !TEMPLATES[template]) {
      return NextResponse.json(
        { error: `Unknown template: ${template}. Known: ${TEMPLATE_KEYS.join(', ')}` },
        { status: 400 }
      );
    }

    const entry = TEMPLATES[template];
    const element = React.createElement(entry.component, props);
    const html = await render(element, { pretty: false });
    const text = await render(element, { plainText: true });
    const subject = entry.subject(props);

    return NextResponse.json({
      template,
      subject,
      html,
      text,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || String(e) }, { status: 500 });
  }
}
