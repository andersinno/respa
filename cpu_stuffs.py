current_payload = {
    'ApiVersion': '3.0.0',
    'Source': 'varaamo',  # API key
    'Id': 'axveh5wj566a',  #  Order number
    'Mode': 3,
    'Action': 'new payment',
    'Products': [
        {'Code': 'demo_001', 'Amount': 1, 'Price': 700, 'Description': 'Price for unemployed people'}
    ],  # If the price and vat are not sent, uses the default that exists in CPU
    'Email': '',
    'FirstName': '',
    'LastName': '',
    'ReturnAddress': 'http://localhost:8000/payments/success/?RESPA_UI_RETURN_URL=http%3A%2F%2Flocalhost%3A3000%2Freservation-payment-return',
    'NotificationAddress': 'http://localhost:8000/payments/notify/',
    'Hash': 'b9f89738e97e2d4935fc6f0981ae73566ff157ec1b96e0051d010faaece967aa'
}

response_from_cpu = {
    'Id': 'axveh5wj566a',
    'Status': 2,
    'Reference': '2234',
    'Action': 'new payment',
    'PaymentAddress': 'https://verkkomaksutesti.cpu.fi/kassa/order-pay/2234/?pay_for_order=true&key=wc_order_yCTAu4OERHf8X',
    'PaymentExpires': '202210051048',
    'Hash': '36268d93f3ff0cab06e423e60b044d037defa2717d528c835b83ec1eff2fa359'
}

# User redirected to pay to PaymentAddress
# riku.koffert@cpu.fi

"""
1. Can there be multiple products in a reservation ? E.g. reserving a library table and computer in a single reservation.
    Can a resource have multiple products ? The code supports multiple product per resource in backend.
    If a reservation can have multiple products; Will all the products have same VAT ?
    How would we select multiple products in the frontend?

2. Recurring reservation ? How to do it.
    Doesn't seem to work to me.

3. If a pricelist has 'request processing' field set to True, all the reservations would go to
    resource admins for check (no direct reservations). Does it mean only when the reservation is approved
    they get the payment link and it is forwarded to User via email ?
    
4. How many of the events and user groups we would have in the end ? If it's too many need a way
    to tie it to City/municipality.
    
5. Ask Sari about the translations of placement for the frontend

#TODO: Add the items of pricelists
lowest VAT%; higher price
"""
