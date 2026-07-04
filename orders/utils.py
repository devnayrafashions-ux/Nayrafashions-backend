from django.core.mail import send_mail
from django.conf import settings


def send_shipment_email(order):
    """
    Sends a "Your order has shipped" email to the customer, including
    tracking number and courier name. Called from AdminOrderDetailView
    whenever an order's status is changed to 'shipped'.

    Uses order.email (the shipping email captured at checkout) rather
    than order.user.email, since orders can technically be placed with
    a different contact email than the account email.
    """
    subject = f"Your Nayra Fashions order #{order.order_number} has shipped!"

    tracking_line = (
        f"Tracking Number: {order.tracking_number}\n"
        if order.tracking_number else ""
    )
    courier_line = (
        f"Courier: {order.courier_name}\n"
        if order.courier_name else ""
    )

    message = (
        f"Hi {order.full_name},\n\n"
        f"Good news — your order #{order.order_number} has shipped and is on its way!\n\n"
        f"{tracking_line}"
        f"{courier_line}"
        f"\nShipping to:\n"
        f"{order.address_line1}"
        f"{', ' + order.address_line2 if order.address_line2 else ''}\n"
        f"{order.city}, {order.state} — {order.pincode}\n\n"
        f"Thank you for shopping with Nayra Fashions!\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.email],
        fail_silently=True,  # NEW: don't let a broken email config crash the status update
    )