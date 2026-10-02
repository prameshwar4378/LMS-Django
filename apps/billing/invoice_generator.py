import io
from datetime import datetime
from django.db import transaction, IntegrityError
from apps.billing.models import Invoice
from apps.billing.services import calculate_stay_bill, generate_unique_invoice_number
from apps.settings_app.models import Settings
from apps.stays.models import Stay

def get_or_create_invoice_for_stay(stay, prop=None):
    """
    Retrieves the existing invoice for the stay or creates a new one
    if the stay is checked out. Returns (invoice, bill, settings_obj, error_message).
    """
    if not prop:
        prop = stay.property
    settings_obj = Settings.get_settings(prop=prop)
    bill = calculate_stay_bill(stay)

    invoice = getattr(stay, 'invoice', None) or Invoice.objects.filter(stay=stay).first()
    if not invoice:
        if stay.status != Stay.Status.CHECKED_OUT and not stay.actual_checkout_date:
            return None, bill, settings_obj, "Invoice can only be generated after checkout is completed."

        inv_number = generate_unique_invoice_number(prop, settings_obj.invoice_prefix)
        for _ in range(10):
            try:
                with transaction.atomic():
                    invoice, _ = Invoice.objects.get_or_create(
                        stay=stay,
                        defaults={
                            'property': prop,
                            'invoice_number': inv_number,
                            'subtotal': bill.get('gross_subtotal', bill.get('subtotal', 0)),
                            'discount': bill.get('discount_amount', 0),
                            'tax': bill.get('gst_amount', bill.get('tax_amount', 0)),
                            'grand_total': bill.get('grand_total', 0),
                            'paid_amount': bill.get('total_paid', 0),
                            'balance': bill.get('balance', 0),
                        }
                    )
                break
            except IntegrityError:
                inv_number = generate_unique_invoice_number(prop, settings_obj.invoice_prefix)

    return invoice, bill, settings_obj, None


def render_invoice_html(stay, invoice, bill, settings_obj, is_for_pdf=False, autoprint=False):
    """
    Renders clean, self-contained HTML for the Tax Invoice.
    Compatible with xhtml2pdf (table-based, standard CSS 2.1)
    and browser printing (with responsive preview & print action).
    """
    cust = stay.primary_customer
    room = stay.room
    room_type_name = room.room_type.name if room and room.room_type else "Standard"
    room_number = room.room_number if room else "—"

    # Format dates
    check_in_str = f"{stay.check_in_date}"
    if stay.check_in_time:
        check_in_str += f" {stay.check_in_time.strftime('%H:%M')}"

    out_date = stay.actual_checkout_date or stay.expected_checkout_date
    checkout_str = f"{out_date}" if out_date else ""
    if stay.actual_checkout_time:
        checkout_str += f" {stay.actual_checkout_time.strftime('%H:%M')}"

    inv_date_str = invoice.generated_at.strftime('%d/%m/%Y') if invoice and invoice.generated_at else datetime.now().strftime('%d/%m/%Y')
    inv_num_str = invoice.invoice_number if invoice else "PROFORMA"

    currency = "Rs." if is_for_pdf else (settings_obj.currency or "Rs.")

    # Extra charges rows
    extra_charges = stay.extra_charges.all().order_by('created_at')
    extra_rows_html = ""
    item_counter = 2
    for ec in extra_charges:
        desc = ec.description or (ec.charge_type.name if ec.charge_type else "Extra Service")
        qty = ec.quantity or 1
        rate = float(ec.unit_price or 0)
        amt = float(ec.amount or 0)
        extra_rows_html += f"""
        <tr>
            <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px 8px;">{item_counter}</td>
            <td style="border: 1px solid #cbd5e1; padding: 6px 8px;">{desc}</td>
            <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px 8px;">{qty}</td>
            <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px 8px;">{rate:.2f}</td>
            <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px 8px; font-weight: bold;">{amt:.2f}</td>
        </tr>
        """
        item_counter += 1

    # Payments rows
    payments = stay.payments.all().order_by('payment_date')
    payment_rows_html = ""
    for p in payments:
        p_num = p.payment_number
        p_date = p.payment_date.strftime('%d/%m/%Y %I:%M %p') if p.payment_date else ""
        p_method = p.get_payment_method_display() if hasattr(p, 'get_payment_method_display') else p.payment_method
        p_amt = float(p.amount or 0)
        payment_rows_html += f"""
        <tr>
            <td style="border: 1px solid #cbd5e1; padding: 5px 8px; font-weight: bold;">{p_num}</td>
            <td style="border: 1px solid #cbd5e1; padding: 5px 8px;">{p_date}</td>
            <td style="border: 1px solid #cbd5e1; padding: 5px 8px;"><span style="background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 9.5px;">{p_method}</span></td>
            <td style="text-align: right; border: 1px solid #cbd5e1; padding: 5px 8px; font-weight: bold; color: #166534;">{currency} {p_amt:.2f}</td>
        </tr>
        """

    room_days = bill.get('room_days', 1)
    room_rate = float(bill.get('room_rate', 0))
    room_subtotal = float(bill.get('room_subtotal', 0))
    subtotal = float(bill.get('subtotal', 0))
    discount = float(bill.get('discount_amount', 0))
    discount_reason = bill.get('discount_reason', '')
    tax_amt = float(bill.get('tax_amount', 0))
    tax_pct = bill.get('tax_percentage', 0)
    grand_total = float(bill.get('grand_total', 0))
    total_paid = float(bill.get('total_paid', 0))
    balance = float(bill.get('balance', 0))

    discount_row = ""
    if discount > 0:
        d_label = f"Discount ({discount_reason})" if discount_reason else "Discount"
        discount_row = f"""
        <tr>
            <td style="padding: 4px 8px; color: #dc2626;">{d_label}:</td>
            <td style="text-align: right; padding: 4px 8px; font-weight: bold; color: #dc2626;">-{currency} {discount:.2f}</td>
        </tr>
        """

    tax_row = ""
    if tax_amt > 0:
        tax_row = f"""
        <tr>
            <td style="padding: 4px 8px; color: #475569;">GST Tax ({tax_pct}%):</td>
            <td style="text-align: right; padding: 4px 8px; font-weight: bold; color: #0f172a;">{currency} {tax_amt:.2f}</td>
        </tr>
        """

    balance_color = "#dc2626" if balance > 0.01 else "#166534"
    balance_text = "PAID IN FULL" if balance <= 0.01 else "BALANCE DUE"

    # Guest details
    cust_name = cust.full_name if cust else "Guest"
    cust_mobile = cust.mobile if cust and cust.mobile else "N/A"
    cust_address = cust.address if cust and cust.address else "N/A"
    cust_id_info = f"{cust.id_type or 'ID'}: {cust.id_number or 'N/A'}" if cust else "N/A"

    # Lodge branding
    lodge_name = settings_obj.lodge_name or "InnVetrix Hospitality"
    lodge_address = settings_obj.address or ""
    lodge_contact = f"Phone: {settings_obj.phone or 'N/A'}"
    if settings_obj.email:
        lodge_contact += f" | Email: {settings_obj.email}"
    gst_str = f"GSTIN: {settings_obj.gst_number}" if settings_obj.gst_number else ""

    print_script = ""
    action_bar_html = ""
    if not is_for_pdf:
        action_bar_html = f"""
        <div class="no-print" style="background: #1e293b; color: white; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-radius: 8px;">
            <div style="font-weight: 600; font-size: 14px;">Official Tax Invoice &bull; {inv_num_str}</div>
            <div style="display: flex; gap: 10px;">
                <a href="?format=pdf" style="background: #2563eb; color: white; padding: 7px 16px; border-radius: 6px; text-decoration: none; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">
                    &#128190; Download PDF
                </a>
                <button onclick="window.print()" style="background: #10b981; color: white; border: none; padding: 7px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">
                    &#128424; Print Invoice
                </button>
            </div>
        </div>
        """
        if autoprint:
            print_script = """
            <script>
                window.addEventListener('load', function() {
                    setTimeout(function() { window.print(); }, 400);
                });
            </script>
            """

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tax Invoice - {inv_num_str}</title>
<style>
    @page {{
        size: a4 portrait;
        margin: 10mm 12mm 12mm 12mm;
    }}
    * {{
        box-sizing: border-box;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #0f172a;
        background-color: {"#f8fafc" if not is_for_pdf else "#ffffff"};
        font-size: 11px;
        line-height: 1.4;
        margin: 0;
        padding: {"20px" if not is_for_pdf else "0"};
    }}
    .invoice-wrapper {{
        max-width: 800px;
        margin: 0 auto;
        background: #ffffff;
        padding: {"24px" if not is_for_pdf else "0"};
        border-radius: {"12px" if not is_for_pdf else "0"};
        box-shadow: {"0 4px 20px rgba(0,0,0,0.06)" if not is_for_pdf else "none"};
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
    }}
    .header-table td {{
        vertical-align: top;
    }}
    .lodge-name {{
        font-size: 19px;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.3px;
        margin-bottom: 2px;
    }}
    .lodge-sub {{
        font-size: 11px;
        color: #475569;
        margin-bottom: 2px;
    }}
    .gst-tag {{
        display: inline-block;
        font-weight: 700;
        color: #0f172a;
        margin-top: 4px;
        font-size: 11px;
    }}
    .invoice-badge {{
        background-color: #f1f5f9;
        border: 1.5px solid #cbd5e1;
        padding: 8px 14px;
        text-align: right;
        border-radius: 6px;
    }}
    .invoice-badge-title {{
        font-size: 9.5px;
        font-weight: 800;
        color: #64748b;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    .invoice-badge-number {{
        font-size: 15px;
        font-weight: 800;
        color: #1d4ed8;
        margin: 2px 0;
    }}
    .invoice-badge-date {{
        font-size: 10.5px;
        color: #334155;
    }}
    .section-box {{
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 9px 12px;
        border-radius: 6px;
    }}
    .section-title {{
        font-size: 10px;
        font-weight: 800;
        color: #1e293b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 4px;
        margin-bottom: 6px;
    }}
    .items-table {{
        margin-top: 14px;
        margin-bottom: 12px;
    }}
    .items-table th {{
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 800;
        font-size: 10.5px;
        padding: 7px 10px;
        border: 1px solid #cbd5e1;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }}
    .summary-card {{
        background-color: #f8fafc;
        border: 1.5px solid #cbd5e1;
        border-radius: 6px;
        padding: 6px;
    }}
    .grand-total-row {{
        background-color: #eff6ff;
        font-weight: 800;
        font-size: 13px;
        color: #1d4ed8;
    }}
    .footer-section {{
        margin-top: 24px;
        border-top: 1px solid #e2e8f0;
        padding-top: 12px;
        text-align: center;
        color: #64748b;
        font-size: 10px;
    }}
    @media print {{
        .no-print {{
            display: none !important;
        }}
        body {{
            background: white !important;
            padding: 0 !important;
        }}
        .invoice-wrapper {{
            box-shadow: none !important;
            padding: 0 !important;
            max-width: 100% !important;
        }}
    }}
</style>
</head>
<body>
    {action_bar_html}
    <div class="invoice-wrapper">
        <!-- 1. Header with Lodge Info and Invoice Badge -->
        <table class="header-table" style="margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">
            <tr>
                <td style="width: 62%;">
                    <div class="lodge-name">{lodge_name}</div>
                    {f'<div class="lodge-sub">{lodge_address}</div>' if lodge_address else ''}
                    <div class="lodge-sub">{lodge_contact}</div>
                    {f'<div class="gst-tag">{gst_str}</div>' if gst_str else ''}
                </td>
                <td style="width: 38%;">
                    <div class="invoice-badge">
                        <div class="invoice-badge-title">TAX INVOICE / RECEIPT</div>
                        <div class="invoice-badge-number">{inv_num_str}</div>
                        <div class="invoice-badge-date">Date: <strong>{inv_date_str}</strong></div>
                        <div style="font-size: 9.5px; color: #64748b; margin-top: 2px;">Stay #: <strong>{stay.stay_number}</strong></div>
                    </div>
                </td>
            </tr>
        </table>

        <!-- 2. Guest Info & Stay Details -->
        <table style="margin-bottom: 14px;">
            <tr>
                <td style="width: 48.5%; vertical-align: top;">
                    <div class="section-box">
                        <div class="section-title">Billed To (Guest Details)</div>
                        <div style="font-size: 13px; font-weight: 800; color: #0f172a; margin-bottom: 2px;">{cust_name}</div>
                        <div style="color: #475569; font-size: 10.5px;">Mobile: <strong>{cust_mobile}</strong></div>
                        <div style="color: #475569; font-size: 10.5px;">Address: {cust_address}</div>
                        <div style="color: #475569; font-size: 10.5px;">{cust_id_info}</div>
                    </div>
                </td>
                <td style="width: 3%;"></td>
                <td style="width: 48.5%; vertical-align: top;">
                    <div class="section-box">
                        <div class="section-title">Stay & Accommodation Details</div>
                        <div style="font-size: 12px; font-weight: 800; color: #1d4ed8; margin-bottom: 2px;">
                            Room {room_number} &bull; {room_type_name}
                        </div>
                        <table style="font-size: 10.5px; width: 100%;">
                            <tr>
                                <td style="color: #64748b; width: 35%;">Check-In:</td>
                                <td style="font-weight: 600;">{check_in_str}</td>
                            </tr>
                            <tr>
                                <td style="color: #64748b;">Check-Out:</td>
                                <td style="font-weight: 600;">{checkout_str}</td>
                            </tr>
                            <tr>
                                <td style="color: #64748b;">Duration:</td>
                                <td style="font-weight: 700; color: #0f172a;">{room_days} Night(s)</td>
                            </tr>
                        </table>
                    </div>
                </td>
            </tr>
        </table>

        <!-- 3. Line Items Table -->
        <table class="items-table">
            <thead>
                <tr>
                    <th style="width: 6%; text-align: center;">#</th>
                    <th style="width: 48%;">Service / Item Description</th>
                    <th style="width: 14%; text-align: center;">Qty / Nights</th>
                    <th style="width: 16%; text-align: right;">Rate ({currency})</th>
                    <th style="width: 16%; text-align: right;">Amount ({currency})</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px 8px;">1</td>
                    <td style="border: 1px solid #cbd5e1; padding: 6px 8px;">
                        <strong style="color: #0f172a;">Room Accommodation &bull; Room {room_number}</strong>
                        <div style="font-size: 9.5px; color: #64748b;">{room_type_name} &bull; {room_days} Night(s) @ {currency} {room_rate:.2f}/night</div>
                    </td>
                    <td style="text-align: center; border: 1px solid #cbd5e1; padding: 6px 8px; font-weight: 600;">{room_days}</td>
                    <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px 8px;">{room_rate:.2f}</td>
                    <td style="text-align: right; border: 1px solid #cbd5e1; padding: 6px 8px; font-weight: 800; color: #0f172a;">{room_subtotal:.2f}</td>
                </tr>
                {extra_rows_html}
            </tbody>
        </table>

        <!-- 4. Financial Summary & Settlement Status -->
        <table style="margin-top: 10px;">
            <tr>
                <td style="width: 52%; vertical-align: top;">
                    <div class="section-box" style="margin-bottom: 10px;">
                        <div class="section-title">Folio Settlement Status</div>
                        <div style="font-size: 13px; font-weight: 800; color: {balance_color}; margin-bottom: 4px;">
                            &bull; {balance_text}
                        </div>
                        <div style="font-size: 10px; color: #64748b;">
                            Total billed amount has been settled according to the payment records shown below.
                        </div>
                    </div>
                </td>
                <td style="width: 3%;"></td>
                <td style="width: 45%; vertical-align: top;">
                    <div class="summary-card">
                        <table style="font-size: 11px; width: 100%;">
                            <tr>
                                <td style="padding: 4px 8px; color: #475569;">Gross Subtotal:</td>
                                <td style="text-align: right; padding: 4px 8px; font-weight: 700;">{currency} {subtotal:.2f}</td>
                            </tr>
                            {discount_row}
                            {tax_row}
                            <tr class="grand-total-row">
                                <td style="padding: 6px 8px; border-top: 1px solid #93c5fd; border-bottom: 1px solid #93c5fd;">Grand Total:</td>
                                <td style="text-align: right; padding: 6px 8px; border-top: 1px solid #93c5fd; border-bottom: 1px solid #93c5fd;">{currency} {grand_total:.2f}</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 8px; font-weight: 600; color: #166534;">Total Paid / Advance:</td>
                                <td style="text-align: right; padding: 4px 8px; font-weight: 700; color: #166534;">{currency} {total_paid:.2f}</td>
                            </tr>
                            <tr style="border-top: 1.5px solid #cbd5e1;">
                                <td style="padding: 5px 8px; font-weight: 800; color: #0f172a;">Balance Due:</td>
                                <td style="text-align: right; padding: 5px 8px; font-weight: 800; color: {balance_color}; font-size: 12.5px;">{currency} {balance:.2f}</td>
                            </tr>
                        </table>
                    </div>
                </td>
            </tr>
        </table>

        <!-- 5. Payment Transactions Table -->
        {f'''
        <div style="margin-top: 14px;">
            <div class="section-title" style="margin-bottom: 6px;">Payment Transactions Recorded</div>
            <table style="width: 100%; border: 1px solid #cbd5e1; font-size: 10.5px;">
                <thead>
                    <tr style="background-color: #f1f5f9; font-weight: 800;">
                        <th style="border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left;">Receipt / Payment #</th>
                        <th style="border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left;">Date & Time</th>
                        <th style="border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left;">Payment Method</th>
                        <th style="border: 1px solid #cbd5e1; padding: 5px 8px; text-align: right;">Amount Paid</th>
                    </tr>
                </thead>
                <tbody>
                    {payment_rows_html}
                </tbody>
            </table>
        </div>
        ''' if payment_rows_html else ''}

        <!-- 6. Footer and Signoff -->
        <table style="margin-top: 25px; width: 100%;">
            <tr>
                <td style="width: 50%; vertical-align: bottom; font-size: 10px; color: #64748b;">
                    <strong>Thank you for staying with us!</strong><br>
                    We hope you enjoyed your visit. Have a safe journey!
                </td>
                <td style="width: 50%; text-align: right; vertical-align: bottom; font-size: 10px;">
                    <div style="height: 35px;"></div>
                    <div style="border-top: 1px dashed #94a3b8; display: inline-block; padding-top: 4px; min-width: 160px; text-align: center;">
                        <strong>Authorized Signatory / Cashier</strong>
                    </div>
                </td>
            </tr>
        </table>

        <div class="footer-section">
            This is a computer-generated tax invoice & folio receipt issued by {lodge_name}.
        </div>
    </div>
    {print_script}
</body>
</html>
"""
    return html


def generate_invoice_pdf_bytes(stay, invoice, bill, settings_obj):
    """
    Renders invoice HTML and generates PDF bytes using xhtml2pdf.
    """
    from xhtml2pdf import pisa
    html_content = render_invoice_html(stay, invoice, bill, settings_obj, is_for_pdf=True)
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer, encoding='utf-8')
    if pisa_status.err:
        raise Exception(f"PDF generation failed with code {pisa_status.err}")
    return pdf_buffer.getvalue()
