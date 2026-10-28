
import logging
from html import escape
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


logger = logging.getLogger(__name__)

MAROON = "#7B1B1B"
DARK_MAROON = "#542323"
GOLD = "#C9A45C"
CREAM = "#FBF6EF"
TEXT_COLOR = "#574843"


def _money(value):
    return f"₹{float(value or 0):,.2f}"


def _logo_html():
    """
    Set NAYRA_EMAIL_LOGO_URL in Django settings to an absolute,
    publicly accessible HTTPS URL for your Nayra Fashions logo.
    """
    logo_url = getattr(settings, "NAYRA_EMAIL_LOGO_URL", "")

    if not logo_url:
        return """
        <div style="font-family:Georgia,serif;font-size:30px;
                    font-weight:bold;letter-spacing:5px;
                    color:#7B1B1B;text-align:center;">
            NAYRA
        </div>
        <div style="font-family:Georgia,serif;font-size:15px;
                    font-weight:bold;letter-spacing:3px;
                    color:#7B1B1B;text-align:center;">
            FASHIONS
        </div>
        <div style="font-size:12px;color:#A87924;text-align:center;
                    margin-top:8px;">
            Where Comfort Meets You
        </div>
        """

    return f"""
    <div style="text-align:center;">
        <img src="{escape(logo_url, quote=True)}"
             alt="Nayra Fashions"
             style="display:block;max-width:240px;width:100%;
                    height:auto;margin:0 auto 10px;">
        <div style="font-family:Georgia,serif;font-size:12px;
                    color:#7B1B1B;">
            Where Comfort Meets You
        </div>
    </div>
    """


def _email_template(title, greeting, body, content, footer=None):
    footer = footer or "Thank you for choosing Nayra Fashions."

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:{CREAM};
                 font-family:Arial,Helvetica,sans-serif;color:{TEXT_COLOR};">
      <table role="presentation" width="100%" cellspacing="0"
             cellpadding="0" style="background:{CREAM};padding:28px 10px;">
        <tr>
          <td align="center">
            <table role="presentation" width="600" cellspacing="0"
                   cellpadding="0"
                   style="width:100%;max-width:600px;background:#ffffff;
                          border:1px solid #eadfd3;">
              <tr>
                <td style="padding:28px 24px 20px;">
                  {_logo_html()}
                </td>
              </tr>
              <tr>
                <td style="height:3px;background:{GOLD};"></td>
              </tr>
              <tr>
                <td style="padding:28px 24px;">
                  <h1 style="font-family:Georgia,serif;font-size:25px;
                             line-height:1.3;color:{DARK_MAROON};
                             font-weight:normal;margin:0 0 22px;">
                    {escape(title)}
                  </h1>
                  <p style="font-size:15px;line-height:1.8;margin:0 0 12px;">
                    Hi {escape(str(greeting or "Customer"))},
                  </p>
                  <p style="font-size:15px;line-height:1.8;margin:0 0 22px;">
                    {body}
                  </p>
                  {content}
                  <p style="font-size:14px;line-height:1.8;margin:24px 0 0;">
                    {escape(footer)}
                  </p>
                </td>
              </tr>
              <tr>
                <td style="background:{CREAM};padding:18px 24px;
                           text-align:center;border-top:1px solid #eadfd3;">
                  <p style="font-size:12px;color:#86766c;margin:0;">
                    Nayra Fashions · Where Comfort Meets You
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def send_order_confirmation_email(order):
    """
    Send order confirmation after successful payment verification.
    Uses the email entered by the customer at checkout.
    """
    subject = f"Order Confirmed | Nayra Fashions #{order.order_number}"

    item_rows = []

    for item in order.items.all():
        name = escape(str(item.product_name))
        size = escape(str(item.size or ""))
        color = escape(str(item.color or ""))

        details = []
        if size:
            details.append(f"Size: {size}")
        if color:
            details.append(f"Color: {color}")

        item_rows.append(f"""
        <tr>
          <td style="padding:13px 8px;border-bottom:1px solid #eee5dc;">
            <div style="font-size:14px;font-weight:bold;color:{DARK_MAROON};">
              {name}
            </div>
            <div style="font-size:12px;color:#86766c;margin-top:5px;">
              {" · ".join(details)}
            </div>
          </td>
          <td align="center"
              style="padding:13px 6px;border-bottom:1px solid #eee5dc;
                     font-size:14px;">
            {item.quantity}
          </td>
          <td align="right"
              style="padding:13px 8px;border-bottom:1px solid #eee5dc;
                     font-size:14px;white-space:nowrap;">
            {_money(item.product_price)}
          </td>
          <td align="right"
              style="padding:13px 8px;border-bottom:1px solid #eee5dc;
                     font-size:14px;white-space:nowrap;">
            {_money(item.subtotal)}
          </td>
        </tr>
        """)

    items_html = "".join(item_rows)

    address_lines = [
        order.full_name, order.address_line1, order.address_line2,
        f"{order.city}, {order.state} {order.pincode}", f"Phone: {order.phone}",
    ]
    address_html = "<br>".join(escape(str(l)) for l in address_lines if l)

    order_details = f"""
    <div style="background:{CREAM};padding:16px;margin-bottom:22px;
                border:1px solid #eee5dc;">
      <div style="font-size:12px;color:#86766c;margin-bottom:6px;">
        ORDER NUMBER
      </div>
      <div style="font-size:19px;font-weight:bold;color:{MAROON};">
        {escape(str(order.order_number))}
      </div>
    </div>

    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="border-collapse:collapse;margin-bottom:20px;">
      <thead>
        <tr style="background:{CREAM};">
          <th align="left" style="padding:10px 8px;font-size:12px;">ITEM</th>
          <th align="center" style="padding:10px 6px;font-size:12px;">QTY</th>
          <th align="right" style="padding:10px 8px;font-size:12px;">PRICE</th>
          <th align="right" style="padding:10px 8px;font-size:12px;">TOTAL</th>
        </tr>
      </thead>
      <tbody>{items_html}</tbody>
    </table>

    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td style="padding:7px 0;font-size:14px;">Subtotal</td>
        <td align="right" style="padding:7px 0;font-size:14px;">
          {_money(order.subtotal)}
        </td>
      </tr>
      <tr>
        <td style="padding:7px 0;font-size:14px;">Shipping</td>
        <td align="right" style="padding:7px 0;font-size:14px;">
          {_money(order.shipping_charge)}
        </td>
      </tr>
      <tr>
        <td style="padding:15px 0;border-top:1px solid {GOLD};
                   font-size:17px;font-weight:bold;color:{MAROON};">
          Order Total
        </td>
        <td align="right"
            style="padding:15px 0;border-top:1px solid {GOLD};
                   font-size:18px;font-weight:bold;color:{MAROON};">
          {_money(order.total)}
        </td>
      </tr>
    </table>

    <div style="margin-top:22px;padding:16px;background:{CREAM};
                border:1px solid #eee5dc;border-left:3px solid {GOLD};">
      <div style="font-size:12px;color:#86766c;margin-bottom:6px;">
        DELIVERING TO
      </div>
      <div style="font-size:14px;line-height:1.7;">{address_html}</div>
    </div>
    """

    html_message = _email_template(
        title="Thank you for your order!",
        greeting=order.full_name,
        body=(
            "Your payment has been confirmed and your order is placed. "
            "Here is a summary of the items you ordered."
        ),
        content=order_details,
    )

    plain_message = (
        f"Hi {order.full_name},\n\n"
        f"Your Nayra Fashions order #{order.order_number} is confirmed.\n\n"
        + "\n".join(
            f"{item.product_name} | Qty: {item.quantity} | "
            f"Price: {_money(item.product_price)} | "
            f"Total: {_money(item.subtotal)}"
            for item in order.items.all()
        )
        + f"\n\nSubtotal: {_money(order.subtotal)}"
        + f"\nShipping: {_money(order.shipping_charge)}"
        + f"\nOrder Total: {_money(order.total)}"
        + "\n\nDelivering to:\n" + "\n".join(l for l in address_lines if l)
        + "\n\nThank you for choosing Nayra Fashions."
    )

    return _send_branded_email(
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
        recipient=order.email,
    )


def _safe_tracking_url(url):
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url
    return ""


def send_shipment_email(order):
    """
    Shipment email. Sent only when a tracking ID exists. The admin workflow
    (orders/admin.py) calls this once, when an order first becomes
    'shipped' with tracking info.
    """
    tracking_number = (order.tracking_number or "").strip()
    if not tracking_number:
        logger.warning("Shipment email skipped for %s: no tracking ID",
                       order.order_number)
        return False

    subject = f"Your Order Has Shipped | Nayra Fashions #{order.order_number}"
    tracking_url = _safe_tracking_url(order.tracking_url)
    courier = escape(str(order.courier_name or "Our courier partner"))

    tracking_button = ""
    if tracking_url:
        tracking_button = f"""
        <div style="text-align:center;margin:26px 0 8px;">
          <a href="{escape(tracking_url, quote=True)}" target="_blank"
             style="display:inline-block;background:{MAROON};color:#ffffff;
                    text-decoration:none;font-size:14px;font-weight:bold;
                    letter-spacing:1px;padding:15px 30px;
                    border:2px solid {GOLD};border-radius:3px;">
            Track Your Shipment
          </a>
        </div>
        """

    content = f"""
    <div style="background:{CREAM};padding:20px;border:1px solid #eee5dc;
                border-top:3px solid {GOLD};">
      <p style="font-size:12px;color:#86766c;margin:0 0 6px;">ORDER NUMBER</p>
      <p style="font-size:18px;font-weight:bold;color:{MAROON};margin:0 0 18px;">
        {escape(str(order.order_number))}
      </p>
      <p style="font-size:12px;color:#86766c;margin:0 0 6px;">COURIER PARTNER</p>
      <p style="font-size:15px;font-weight:bold;margin:0 0 18px;">{courier}</p>
      <p style="font-size:12px;color:#86766c;margin:0 0 6px;">
        TRACKING ID (tap and hold to copy)
      </p>
      <p style="font-family:'Courier New',monospace;font-size:20px;
                font-weight:bold;color:{MAROON};margin:0;padding:10px 12px;
                background:#ffffff;border:1px dashed {GOLD};
                letter-spacing:1px;word-break:break-all;
                -webkit-user-select:all;user-select:all;">
        {escape(tracking_number)}
      </p>
    </div>
    {tracking_button}
    """

    html_message = _email_template(
        title="Your order is on its way!",
        greeting=order.full_name,
        body=(
            "Good news! Your Nayra Fashions order has been shipped. "
            "Use the tracking details below to follow your delivery."
        ),
        content=content,
    )

    plain_message = (
        f"Hi {order.full_name},\n\n"
        f"Your order #{order.order_number} has shipped!\n\n"
        f"Courier: {order.courier_name or 'Our courier partner'}\n"
        f"Tracking ID: {tracking_number}\n"
        + (f"Track your shipment: {tracking_url}\n" if tracking_url else "")
        + "\nThank you for choosing Nayra Fashions."
    )

    return _send_branded_email(
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
        recipient=order.email,
    )


def _send_branded_email(subject, plain_message, html_message, recipient):
    """
    Send plain-text + HTML. Returns False (and logs) on failure so an email
    problem can never break checkout or admin saves.
    """
    if not recipient:
        return False

    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or None
    )

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=[recipient],
        )
        message.attach_alternative(html_message, "text/html")
        return bool(message.send(fail_silently=False))
    except Exception:
        logger.exception("Unable to send Nayra Fashions email to %s", recipient)
        return False
