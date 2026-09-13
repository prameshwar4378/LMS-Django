import logging
import threading
import re
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)

def _clean_phone_for_wa(phone: str) -> str:
    digits = re.sub(r'\D', '', str(phone or ''))
    if len(digits) == 10:
        return '91' + digits
    return digits

def _build_admin_email(data: dict) -> tuple:
    """
    Builds Subject, Text, and HTML for the Official Ultoxy Admin Notification.
    """
    subject = f"🔔 [InnVetrix Lead Alert] New Demo Request: {data.get('property_name', 'Property')} ({data.get('full_name', 'Lead')})"
    
    clean_phone = _clean_phone_for_wa(data.get('phone', ''))
    wa_link = f"https://wa.me/{clean_phone}" if clean_phone else "#"
    
    text_body = f"""==================================================
INNVETRIX HOSPITALITY CLOUD - NEW INQUIRY RECEIVED
Ultoxy Technologies Lead Routing Notification
==================================================

Property Name:     {data.get('property_name')}
Contact Person:    {data.get('full_name')}
Room Count:        {data.get('room_count')} Rooms
Contact Phone:     {data.get('phone')}
Contact Email:     {data.get('email')}
City / Location:   {data.get('city') or 'Not Specified'}
Interest / Focus:  {data.get('service_interest_display')}

Special Notes / Requirements:
{data.get('message') or 'No additional notes provided.'}

--------------------------------------------------
Lead Technical Metadata:
Source IP:         {data.get('ip_address') or 'Unknown'}
Submitted At:      {data.get('created_at')}

Quick Actions:
- Call Directly: tel:{data.get('phone')}
- WhatsApp Chat: {wa_link}
- Reply via Email: mailto:{data.get('email')}
=================================================="""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New InnVetrix Demo Lead</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f1f5f9;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b0f19; padding: 30px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 620px; background-color: #131b2e; border: 1px solid #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.5);">
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); padding: 32px 28px; text-align: left; border-bottom: 2px solid rgba(129, 140, 248, 0.2);">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <span style="background: rgba(99, 102, 241, 0.25); border: 1px solid rgba(129, 140, 248, 0.4); color: #c7d2fe; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; padding: 4px 12px; border-radius: 999px; display: inline-block; margin-bottom: 12px;">
                      ⚡ Immediate Lead Alert
                    </span>
                    <h1 style="margin: 0 0 6px 0; font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                      InnVetrix Cloud PMS
                    </h1>
                    <p style="margin: 0; font-size: 13px; color: #a5b4fc; font-weight: 500;">
                      Ultoxy Technologies Lead Dispatch Engine
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Summary Highlights -->
          <tr>
            <td style="padding: 28px 28px 12px 28px;">
              <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 12px; padding: 18px 20px; margin-bottom: 24px;">
                <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8;">
                  Prospective Client
                </p>
                <h2 style="margin: 0 0 4px 0; font-size: 20px; color: #38bdf8; font-weight: 700;">
                  {escape(str(data.get('property_name', '')))}
                </h2>
                <p style="margin: 0; font-size: 14px; color: #cbd5e1;">
                  Contact: <strong style="color: #ffffff;">{escape(str(data.get('full_name', '')))}</strong> &bull; Capacity: <strong style="color: #a78bfa;">{escape(str(data.get('room_count', '')))} Rooms</strong>
                </p>
              </div>

              <!-- Details Table -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="border-collapse: separate; border-spacing: 0; border: 1px solid #24324d; border-radius: 10px; overflow: hidden; margin-bottom: 24px;">
                <tr style="background: #18233a;">
                  <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; width: 35%; border-bottom: 1px solid #24324d;">Phone Number</td>
                  <td style="padding: 12px 16px; font-size: 14px; font-weight: 700; color: #ffffff; border-bottom: 1px solid #24324d;">
                    <a href="tel:{escape(str(data.get('phone', '')))}" style="color: #38bdf8; text-decoration: none;">{escape(str(data.get('phone', '')))}</a>
                  </td>
                </tr>
                <tr style="background: #141c2e;">
                  <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; border-bottom: 1px solid #24324d;">Email Address</td>
                  <td style="padding: 12px 16px; font-size: 14px; color: #ffffff; border-bottom: 1px solid #24324d;">
                    <a href="mailto:{escape(str(data.get('email', '')))}" style="color: #818cf8; text-decoration: none;">{escape(str(data.get('email', '')))}</a>
                  </td>
                </tr>
                <tr style="background: #18233a;">
                  <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; border-bottom: 1px solid #24324d;">Location / City</td>
                  <td style="padding: 12px 16px; font-size: 14px; color: #e2e8f0; border-bottom: 1px solid #24324d;">
                    {escape(str(data.get('city') or 'Not Specified'))}
                  </td>
                </tr>
                <tr style="background: #141c2e;">
                  <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; border-bottom: 1px solid #24324d;">Solution Interest</td>
                  <td style="padding: 12px 16px; font-size: 14px; font-weight: 600; color: #34d399; border-bottom: 1px solid #24324d;">
                    {escape(str(data.get('service_interest_display', '')))}
                  </td>
                </tr>
                <tr style="background: #18233a;">
                  <td style="padding: 12px 16px; font-size: 13px; font-weight: 600; color: #94a3b8;">Client Notes</td>
                  <td style="padding: 12px 16px; font-size: 13px; line-height: 1.5; color: #cbd5e1;">
                    {escape(str(data.get('message') or 'No additional notes provided.'))}
                  </td>
                </tr>
              </table>

              <!-- Action Buttons -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                <tr>
                  <td align="center" style="padding: 6px;">
                    <a href="https://wa.me/{clean_phone}?text=Hello%20{escape(str(data.get('full_name', '')))}%2C%20thank%20you%20for%20contacting%20InnVetrix%20for%20{escape(str(data.get('property_name', '')))}.%20I%20am%20calling%20regarding%20your%20demo%20request." target="_blank" style="background: #22c55e; color: #ffffff; text-decoration: none; display: block; padding: 12px 20px; border-radius: 8px; font-weight: 700; font-size: 14px; text-align: center;">
                      💬 Open WhatsApp Chat
                    </a>
                  </td>
                  <td align="center" style="padding: 6px;">
                    <a href="tel:{escape(str(data.get('phone', '')))}" style="background: #4f46e5; color: #ffffff; text-decoration: none; display: block; padding: 12px 20px; border-radius: 8px; font-weight: 700; font-size: 14px; text-align: center;">
                      📞 Call Lead ({escape(str(data.get('phone', '')))})
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Audit Metadata -->
              <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
                Received at: {data.get('created_at')} &bull; IP: {data.get('ip_address')} &bull; Lead ID: #{data.get('id')}
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #0d121f; padding: 18px 28px; text-align: center; border-top: 1px solid #1e293b;">
              <p style="margin: 0; font-size: 12px; color: #64748b;">
                &copy; Ultoxy Technologies &bull; InnVetrix Hospitality Cloud Operations
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, text_body, html_body

def _build_customer_email(data: dict) -> tuple:
    """
    Builds Subject, Text, and HTML for the Customer Confirmation / Acknowledgment.
    """
    property_name = data.get('property_name', 'Your Property')
    full_name = data.get('full_name', 'Esteemed Hotelier')
    subject = f"InnVetrix Demo Request Confirmed for {property_name}"
    
    text_body = f"""Dear {full_name},

Thank you for choosing InnVetrix! We have received your request for a live personalized demonstration of the InnVetrix Cloud Lodge & Hotel Management System for {property_name}.

YOUR REQUEST DETAILS:
- Property: {property_name} ({data.get('room_count')} Rooms)
- Solution Area: {data.get('service_interest_display')}
- Contact Phone: {data.get('phone')}

WHAT HAPPENS NEXT:
1. Rapid Response: A dedicated hospitality technology consultant from Ultoxy Technologies will reach out within 15 minutes to confirm your preferred walkthrough slot.
2. Tailored Sandbox: We prepare a custom demo environment matching your room inventory ({data.get('room_count')} rooms) and operational needs.
3. Zero-Risk Trial: Following the walkthrough, you'll receive immediate trial credentials to experience front-desk speed firsthand.

NEED IMMEDIATE ASSISTANCE?
- Direct Call / WhatsApp: +91 77768 24564
- Official Support: ultoxy.tech@gmail.com
- Visit: https://www.ultoxy.com

Warm regards,
The InnVetrix Team
Ultoxy Technologies | Stay Ahead. Beyond Expectations."""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to InnVetrix</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f1f5f9;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b0f19; padding: 30px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 620px; background-color: #131b2e; border: 1px solid #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.5);">
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); padding: 36px 32px; text-align: center; border-bottom: 2px solid rgba(129, 140, 248, 0.2);">
              <div style="display: inline-block; background: rgba(99, 102, 241, 0.25); border: 1px solid rgba(129, 140, 248, 0.4); border-radius: 999px; padding: 5px 16px; margin-bottom: 14px;">
                <span style="color: #c7d2fe; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px;">
                  ✦ Demo Request Received
                </span>
              </div>
              <h1 style="margin: 0 0 8px 0; font-size: 28px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                Welcome to InnVetrix
              </h1>
              <p style="margin: 0; font-size: 14px; color: #c7d2fe; font-weight: 500;">
                Stay Ahead. Beyond Expectations.
              </p>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 32px 20px 32px;">
              <p style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #f8fafc;">
                Dear <strong style="color: #38bdf8;">{escape(str(full_name))}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.7; color: #cbd5e1;">
                Thank you for your interest in the <strong>InnVetrix Cloud Lodge & Hotel Management System</strong>. We have successfully received your inquiry for <strong style="color: #ffffff;">{escape(str(property_name))}</strong>.
              </p>

              <!-- Reservation / Inquiry Confirmation Card -->
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background: rgba(30, 41, 59, 0.6); border: 1px solid #334155; border-radius: 12px; margin-bottom: 28px; overflow: hidden;">
                <tr>
                  <td style="padding: 18px 22px;">
                    <p style="margin: 0 0 10px 0; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8;">
                      Inquiry Summary
                    </p>
                    <table width="100%" border="0" cellspacing="0" cellpadding="4">
                      <tr>
                        <td style="color: #94a3b8; font-size: 13px; width: 40%;">Property:</td>
                        <td style="color: #ffffff; font-size: 14px; font-weight: 600;">{escape(str(property_name))}</td>
                      </tr>
                      <tr>
                        <td style="color: #94a3b8; font-size: 13px;">Room Capacity:</td>
                        <td style="color: #38bdf8; font-size: 14px; font-weight: 600;">{escape(str(data.get('room_count', '')))} Rooms</td>
                      </tr>
                      <tr>
                        <td style="color: #94a3b8; font-size: 13px;">Solution Focus:</td>
                        <td style="color: #a78bfa; font-size: 14px; font-weight: 600;">{escape(str(data.get('service_interest_display', '')))}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- What's Next Steps -->
              <h3 style="margin: 0 0 16px 0; font-size: 16px; font-weight: 700; color: #ffffff;">
                What to Expect Next:
              </h3>
              
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 28px;">
                <tr>
                  <td style="vertical-align: top; width: 36px; padding-bottom: 16px;">
                    <div style="width: 28px; height: 28px; border-radius: 50%; background: #4f46e5; color: #ffffff; text-align: center; line-height: 28px; font-size: 13px; font-weight: 700;">1</div>
                  </td>
                  <td style="vertical-align: top; padding-bottom: 16px; padding-left: 8px;">
                    <strong style="color: #ffffff; font-size: 14px; display: block;">15-Minute Priority Outreach</strong>
                    <span style="color: #94a3b8; font-size: 13px; line-height: 1.5;">A senior hospitality consultant will call you at <strong style="color: #cbd5e1;">{escape(str(data.get('phone', '')))}</strong> to align on your workflow goals.</span>
                  </td>
                </tr>
                <tr>
                  <td style="vertical-align: top; width: 36px; padding-bottom: 16px;">
                    <div style="width: 28px; height: 28px; border-radius: 50%; background: #4f46e5; color: #ffffff; text-align: center; line-height: 28px; font-size: 13px; font-weight: 700;">2</div>
                  </td>
                  <td style="vertical-align: top; padding-bottom: 16px; padding-left: 8px;">
                    <strong style="color: #ffffff; font-size: 14px; display: block;">Personalized 1-on-1 Walkthrough</strong>
                    <span style="color: #94a3b8; font-size: 13px; line-height: 1.5;">We demonstrate tape charts, 1-click check-in, GST invoicing, and room QR menus tailored to {escape(str(property_name))}.</span>
                  </td>
                </tr>
                <tr>
                  <td style="vertical-align: top; width: 36px;">
                    <div style="width: 28px; height: 28px; border-radius: 50%; background: #4f46e5; color: #ffffff; text-align: center; line-height: 28px; font-size: 13px; font-weight: 700;">3</div>
                  </td>
                  <td style="vertical-align: top; padding-left: 8px;">
                    <strong style="color: #ffffff; font-size: 14px; display: block;">Complimentary Sandbox Access</strong>
                    <span style="color: #94a3b8; font-size: 13px; line-height: 1.5;">Get complimentary access to test the front desk speed with your staff with zero setup fees.</span>
                  </td>
                </tr>
              </table>

              <!-- Help Hotline Box -->
              <div style="background: linear-gradient(135deg, rgba(79, 70, 229, 0.12) 0%, rgba(14, 165, 233, 0.12) 100%); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 24px;">
                <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 600; color: #cbd5e1;">
                  Need Immediate Answers or Urgent Onboarding?
                </p>
                <p style="margin: 0 0 14px 0; font-size: 18px; font-weight: 800; color: #38bdf8;">
                  Direct Line: +91 77768 24564
                </p>
                <a href="https://wa.me/917776824564?text=Hello%20InnVetrix%20Team%2C%20I%20have%20submitted%20a%20demo%20request%20for%20{escape(str(property_name))}." target="_blank" style="background: #22c55e; color: #ffffff; text-decoration: none; padding: 10px 22px; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">
                  💬 Chat With Us on WhatsApp
                </a>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #0d121f; padding: 24px 32px; text-align: center; border-top: 1px solid #1e293b;">
              <p style="margin: 0 0 6px 0; font-size: 13px; font-weight: 600; color: #94a3b8;">
                InnVetrix Cloud PMS &bull; Powered by Ultoxy Technologies
              </p>
              <p style="margin: 0 0 10px 0; font-size: 12px; color: #64748b;">
                Official Email: <a href="mailto:ultoxy.tech@gmail.com" style="color: #818cf8; text-decoration: none;">ultoxy.tech@gmail.com</a> &bull; Web: <a href="https://www.ultoxy.com" style="color: #818cf8; text-decoration: none;">www.ultoxy.com</a>
              </p>
              <p style="margin: 0; font-size: 11px; color: #475569;">
                This is an automated confirmation sent to {escape(str(data.get('email', '')))} regarding your demo submission.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, text_body, html_body

def _send_inquiry_emails_worker(data: dict) -> None:
    """
    Background worker function executed on a separate daemon thread.
    Zero impact on Django response time. Never raises unhandled exceptions.
    """
    try:
        admin_to = getattr(settings, 'OFFICIAL_NOTIFICATION_EMAIL', 'ultoxy.tech@gmail.com')
        customer_to = data.get('email')
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'InnVetrix Operations <ultoxy.tech@gmail.com>')
        password = getattr(settings, 'EMAIL_HOST_PASSWORD', '')

        # Build email bodies
        admin_sub, admin_txt, admin_html = _build_admin_email(data)
        cust_sub, cust_txt, cust_html = _build_customer_email(data)

        # Check if SMTP credentials are configured
        if not password:
            logger.info(
                "[InnVetrix Email Worker - SIMULATION MODE] EMAIL_HOST_PASSWORD is empty in .env. "
                "Skipping live SMTP delivery to prevent socket delay. "
                "Inquiry logged for admin (%s) and guest (%s): Property='%s', Phone='%s'.",
                admin_to,
                customer_to,
                data.get('property_name'),
                data.get('phone')
            )
            return

        # 1. Send Admin Notification Email
        try:
            admin_msg = EmailMultiAlternatives(
                subject=admin_sub,
                body=admin_txt,
                from_email=from_email,
                to=[admin_to],
                reply_to=[customer_to] if customer_to else None,
            )
            admin_msg.attach_alternative(admin_html, "text/html")
            admin_msg.send(fail_silently=False)
            logger.info("[InnVetrix Email Worker] Admin notification successfully delivered to %s", admin_to)
        except Exception as exc:
            logger.error("[InnVetrix Email Worker] Failed to deliver Admin notification: %s", str(exc), exc_info=True)

        # 2. Send Customer Confirmation Email (if customer has a valid email)
        if customer_to:
            try:
                cust_msg = EmailMultiAlternatives(
                    subject=cust_sub,
                    body=cust_txt,
                    from_email=from_email,
                    to=[customer_to],
                )
                cust_msg.attach_alternative(cust_html, "text/html")
                cust_msg.send(fail_silently=False)
                logger.info("[InnVetrix Email Worker] Confirmation email successfully delivered to customer: %s", customer_to)
            except Exception as exc:
                logger.error("[InnVetrix Email Worker] Failed to deliver customer confirmation email: %s", str(exc), exc_info=True)

    except Exception as exc:
        logger.error("[InnVetrix Email Worker - Unexpected Error] %s", str(exc), exc_info=True)

def send_inquiry_emails_async(inquiry) -> None:
    """
    Initiates asynchronous email dispatch in a background daemon thread.
    Execution time: < 1ms. Form submission responds instantaneously.
    """
    try:
        # Extract plain dictionary to prevent ORM thread-coupling
        created_str = 'Just now'
        if hasattr(inquiry, 'created_at') and inquiry.created_at:
            created_str = inquiry.created_at.strftime('%d %b %Y, %I:%M %p')

        interest_display = getattr(inquiry, 'get_service_interest_display', lambda: inquiry.service_interest)()

        payload = {
            'id': inquiry.id,
            'full_name': inquiry.full_name,
            'property_name': inquiry.property_name,
            'room_count': inquiry.room_count,
            'phone': inquiry.phone,
            'email': inquiry.email,
            'city': inquiry.city,
            'service_interest': inquiry.service_interest,
            'service_interest_display': interest_display,
            'message': inquiry.message,
            'ip_address': getattr(inquiry, 'ip_address', 'Unknown'),
            'created_at': created_str,
        }

        # Launch daemon thread
        worker_thread = threading.Thread(
            target=_send_inquiry_emails_worker,
            args=(payload,),
            name=f"InnVetrix-EmailWorker-Inquiry-{inquiry.id}",
            daemon=True
        )
        worker_thread.start()
        logger.info("[InnVetrix] Background email thread started for Inquiry #%s (%s)", inquiry.id, inquiry.property_name)
    except Exception as exc:
        logger.error("[InnVetrix] Failed to spawn background email thread: %s", str(exc), exc_info=True)
