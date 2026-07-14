import * as React from 'react';
import {
  Body,
  Container,
  Head,
  Hr,
  Html,
  Img,
  Link,
  Preview,
  Section,
  Text,
} from '@react-email/components';

/**
 * HudShell — shared React Email wrapper with the CA Copilot HUD aesthetic:
 * deep-space background, cyan/violet gradient panels, mono captions.
 *
 * Email clients strip external CSS + drop <style> tags in many cases, so
 * everything is inlined. Colours are hex, not tailwind classes.
 */

const COLORS = {
  bg: '#050810',
  panel: '#0b1220',
  panelBorder: '#123249',
  divider: '#0f2436',
  cyan: '#22d3ee',
  cyanSoft: '#0891b2',
  violet: '#a78bfa',
  violetSoft: '#7c3aed',
  text: '#e2e8f0',
  textSoft: '#94a3b8',
  textDim: '#64748b',
  danger: '#f43f5e',
  amber: '#f59e0b',
  green: '#22c55e',
};

const FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif';
const MONO_STACK =
  'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace';

export interface HudShellProps {
  /** Small mono caption above the headline (e.g. "AUTH · VERIFICATION"). */
  eyebrow: string;
  /** Big headline. */
  headline: string;
  /** Preview text shown by mail clients in the inbox list. */
  preview: string;
  children: React.ReactNode;
}

export const HudShell: React.FC<HudShellProps> = ({ eyebrow, headline, preview, children }) => (
  <Html>
    <Head>
      <meta name="color-scheme" content="dark" />
      <meta name="supported-color-schemes" content="dark" />
    </Head>
    <Preview>{preview}</Preview>
    <Body
      style={{
        backgroundColor: COLORS.bg,
        color: COLORS.text,
        fontFamily: FONT_STACK,
        margin: 0,
        padding: 0,
      }}
    >
      {/* Background aurora effect — a soft radial gradient panel */}
      <Container
        style={{
          maxWidth: 620,
          margin: '0 auto',
          padding: '32px 20px 60px',
        }}
      >
        {/* Brand line */}
        <Section style={{ paddingBottom: 16 }}>
          <table role="presentation" width="100%" cellPadding={0} cellSpacing={0}>
            <tbody>
              <tr>
                <td style={{ verticalAlign: 'middle' }}>
                  <table role="presentation" cellPadding={0} cellSpacing={0}>
                    <tbody>
                      <tr>
                        <td
                          style={{
                            width: 34,
                            height: 34,
                            borderRadius: 8,
                            background: `linear-gradient(135deg, ${COLORS.cyan} 0%, ${COLORS.violet} 100%)`,
                            textAlign: 'center',
                            verticalAlign: 'middle',
                            fontFamily: MONO_STACK,
                            fontSize: 14,
                            fontWeight: 700,
                            color: '#050810',
                          }}
                        >
                          CA
                        </td>
                        <td style={{ paddingLeft: 12 }}>
                          <Text
                            style={{
                              margin: 0,
                              fontFamily: MONO_STACK,
                              fontSize: 11,
                              letterSpacing: 2,
                              color: COLORS.cyan,
                            }}
                          >
                            CA · COPILOT
                          </Text>
                          <Text
                            style={{
                              margin: 0,
                              fontFamily: MONO_STACK,
                              fontSize: 10,
                              color: COLORS.textDim,
                              letterSpacing: 1,
                            }}
                          >
                            INTELLIGENCE TERMINAL
                          </Text>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </td>
                <td style={{ textAlign: 'right', verticalAlign: 'middle' }}>
                  <Text
                    style={{
                      margin: 0,
                      fontFamily: MONO_STACK,
                      fontSize: 10,
                      color: COLORS.textDim,
                      letterSpacing: 1,
                    }}
                  >
                    SIGNAL · ENCRYPTED
                  </Text>
                </td>
              </tr>
            </tbody>
          </table>
        </Section>

        {/* Main HUD panel */}
        <Section
          style={{
            background: `linear-gradient(180deg, rgba(34,211,238,0.06) 0%, rgba(124,58,237,0.04) 100%), ${COLORS.panel}`,
            border: `1px solid ${COLORS.panelBorder}`,
            borderRadius: 14,
            padding: '32px 32px 28px',
          }}
        >
          <Text
            style={{
              margin: 0,
              fontFamily: MONO_STACK,
              fontSize: 11,
              letterSpacing: 2,
              color: COLORS.cyan,
              textTransform: 'uppercase',
            }}
          >
            {eyebrow}
          </Text>
          <Text
            style={{
              margin: '8px 0 24px',
              fontSize: 26,
              lineHeight: 1.25,
              fontWeight: 600,
              color: COLORS.text,
            }}
          >
            {headline}
          </Text>
          <Hr style={{ borderColor: COLORS.divider, margin: '0 0 20px' }} />

          {children}
        </Section>

        {/* Footer */}
        <Section style={{ paddingTop: 20 }}>
          <Text
            style={{
              margin: 0,
              fontFamily: MONO_STACK,
              fontSize: 10,
              color: COLORS.textDim,
              letterSpacing: 1,
              textAlign: 'center',
            }}
          >
            CA COPILOT · NOVA & PARTNERS LLP · MUMBAI, IN
          </Text>
          <Text
            style={{
              margin: '6px 0 0',
              fontFamily: MONO_STACK,
              fontSize: 10,
              color: COLORS.textDim,
              letterSpacing: 1,
              textAlign: 'center',
            }}
          >
            <Link href="https://cacopilot.example.com/preferences" style={{ color: COLORS.textDim }}>
              MANAGE PREFERENCES
            </Link>{' '}
            ·{' '}
            <Link href="https://cacopilot.example.com/unsubscribe" style={{ color: COLORS.textDim }}>
              UNSUBSCRIBE
            </Link>
          </Text>
        </Section>
      </Container>
    </Body>
  </Html>
);

/* ---------- Reusable building blocks ---------- */

export const HudCta: React.FC<{ href: string; label: string; tone?: 'primary' | 'danger' }> = ({
  href,
  label,
  tone = 'primary',
}) => {
  const bg =
    tone === 'danger'
      ? `linear-gradient(135deg, #f43f5e 0%, #a21caf 100%)`
      : `linear-gradient(135deg, ${COLORS.cyan} 0%, ${COLORS.violet} 100%)`;
  return (
    <table role="presentation" cellPadding={0} cellSpacing={0} style={{ margin: '4px 0 8px' }}>
      <tbody>
        <tr>
          <td
            style={{
              background: bg,
              borderRadius: 10,
              padding: '2px',
            }}
          >
            <Link
              href={href}
              style={{
                display: 'inline-block',
                padding: '13px 22px',
                borderRadius: 8,
                color: '#050810',
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: 0.5,
                textDecoration: 'none',
                fontFamily: FONT_STACK,
              }}
            >
              {label} →
            </Link>
          </td>
        </tr>
      </tbody>
    </table>
  );
};

export const HudParagraph: React.FC<{ children: React.ReactNode; muted?: boolean }> = ({
  children,
  muted,
}) => (
  <Text
    style={{
      margin: '0 0 14px',
      fontSize: 15,
      lineHeight: 1.65,
      color: muted ? COLORS.textSoft : COLORS.text,
    }}
  >
    {children}
  </Text>
);

export const HudFactRow: React.FC<{ label: string; value: string; tone?: 'default' | 'good' | 'warn' | 'bad' }> = ({
  label,
  value,
  tone = 'default',
}) => {
  const valueColor =
    tone === 'good' ? COLORS.green : tone === 'warn' ? COLORS.amber : tone === 'bad' ? COLORS.danger : COLORS.text;
  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} style={{ margin: '4px 0' }}>
      <tbody>
        <tr>
          <td
            style={{
              fontFamily: MONO_STACK,
              fontSize: 11,
              letterSpacing: 1.5,
              color: COLORS.textDim,
              paddingBottom: 6,
              paddingRight: 12,
              textTransform: 'uppercase',
              width: '45%',
              verticalAlign: 'top',
            }}
          >
            {label}
          </td>
          <td
            style={{
              fontFamily: MONO_STACK,
              fontSize: 13,
              color: valueColor,
              paddingBottom: 6,
              textAlign: 'right',
              verticalAlign: 'top',
            }}
          >
            {value}
          </td>
        </tr>
      </tbody>
    </table>
  );
};

export const HudPanel: React.FC<{ children: React.ReactNode; tone?: 'default' | 'warn' | 'bad' }> = ({
  children,
  tone = 'default',
}) => {
  const border =
    tone === 'warn' ? '#7c5a19' : tone === 'bad' ? '#7a1e2b' : COLORS.divider;
  const bg =
    tone === 'warn'
      ? 'rgba(245,158,11,0.06)'
      : tone === 'bad'
      ? 'rgba(244,63,94,0.08)'
      : 'rgba(34,211,238,0.04)';
  return (
    <Section
      style={{
        border: `1px solid ${border}`,
        borderRadius: 10,
        padding: '14px 16px',
        margin: '4px 0 18px',
        background: bg,
      }}
    >
      {children}
    </Section>
  );
};

export const brand = { COLORS, FONT_STACK, MONO_STACK };
