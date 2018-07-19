import frappe
import sys
from frappe.utils import getdate, today, add_to_date, flt
from erpnext.setup.setup_wizard.setup_wizard import setup_complete
import requests
from frappe.utils.make_random import add_random_children, get_random
import random
from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request, make_payment_entry
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

CUSTOMERS=[]
ITEMS=frappe.get_all("Item")
WAREHOUSE = frappe.get_all("Warehouse")[1].name
SUPPLIERS=[]

def simulate():
    frappe.flags.mute_emails = True
    #setup_site()
    no_of_days = 365
    sale_factor = 1
    frappe.flags.current_date = add_to_date(today(), days=-no_of_days)
    make_customers(10)
    get_suppliers()
    while(frappe.flags.current_date < today()):
        sys.stdout.write("\rSimulating for {0}".format(frappe.flags.current_date))
        sys.stdout.flush()
        for factor in range(random.randint(0,sale_factor)):
            if random.random() < 0.3:
                make_sales_order(sale_factor)
        frappe.flags.current_date = add_to_date(frappe.flags.current_date, days=1)
        if getdate(frappe.flags.current_date).day%15==0:
            sale_factor+=1
            make_customers(1)
    frappe.db.commit()

def setup_site():
    args = {
        "country": "United States",
        "company_name": "GrowPro LLP",
        "company_abbr": "GP",
        "company_tagline": "We grow like Pro!",                          
        "bank_account": "Chase Bank",
        "currency": "USD",
        "language": "English",
        "time_zone": "PT - America/Los_Angles",
        "fy_start_date": getdate("01-01-2018"),
        "fy_end_date": getdate("31-12-2018"),
        "domains": ["Manufacturing"]
    }
    setup_complete(args)

def make_customers(number):
    data = requests.get("https://randomuser.me/api/", params={"nat":"US","results":number})
    for customer in data.json().get("results"):
        cust = frappe.new_doc("Customer")
        cust.update({
            "salutation": customer.get("name").get("title").title(),
            "customer_name": (customer.get("name").get("first") + " " + customer.get("name").get("last")).title(),
            "customer_type": "Individual",
            "gender": customer.get("gender").title(),
            "email_id": customer.get("email"),
            "mobile_no": customer.get("cell"),
            "image": customer.get("picture").get("large"),
            "address_line1": customer.get("location").get("street"),
            "city": customer.get("location").get("city"),
            "state": customer.get("location").get("state"),
            "pincode": customer.get("location").get("postcode"),
            "country": "United States"
        })                             
        cust.save()
        CUSTOMERS.append(cust.name)

def make_sales_order(sale_factor):
    qty_factor = random.randint(1,(random.randint(1, sale_factor)))
    no_of_items_sold= random.randint(1, 10)
    customer = random.choice(CUSTOMERS)
    sales_order_items = []
    for item in xrange(no_of_items_sold):
        sales_order_items.append({
            "item_code": random.choice(ITEMS).name,
            "qty": random.randint(1, qty_factor),
            "warehouse": WAREHOUSE
        })
    sales_order = frappe.get_doc({
        "doctype": "Sales Order",
        "creation": frappe.flags.current_date,
        "customer": customer,
        "transaction_date": frappe.flags.current_date,
        "order_type": "Shopping Cart",
        "items": sales_order_items
    })
    sales_order.save()
    sales_order.submit()
    so = sales_order

    for item in so.items:
        if item.projected_qty<100:
            reorder_stock(item.item_code)

    if flt(so.per_billed) != 100:
        payment_request = make_payment_request(dt="Sales Order", dn=so.name, recipient_id=so.contact_email,
            submit_doc=True, mute_email=True, use_dummy_message=True)

        payment_entry = frappe.get_doc(make_payment_entry(payment_request.name))
        payment_entry.posting_date = frappe.flags.current_date
        payment_entry.submit()
    si = frappe.get_doc(make_sales_invoice(so.name))
    si.set_posting_time=True
    si.posting_date = frappe.flags.current_date
    for d in si.get("items"):
        if not d.income_account:
            d.income_account = "Sales - {}".format(frappe.db.get_value('Company', si.company, 'abbr'))
    si.set_missing_values()
    make_payment_entries_for_pos_invoice(si)
    si.insert()
    si.submit()

    dn = make_delivery_note(so.name)
    dn.posting_date = frappe.flags.current_date
    dn.insert()
    dn.submit()

def make_payment_entries_for_pos_invoice(si):
	for data in si.payments:
		data.amount = si.outstanding_amount
		return

def reorder_stock(item_code):
    mr = make_material_request(item_code)
    po = make_purchase_order(mr.name)
    po.supplier = random.choice(SUPPLIERS)
    po.transaction_date = frappe.flags.current_date
    po.insert()
    po.submit()
    pr = make_purchase_receipt(po.name)
    pr.transaction_date = frappe.flags.current_date
    pr.insert()
    pr.submit()
    pi = make_purchase_invoice(pr.name)
    pi.transaction_date = frappe.flags.current_date
    pi.insert()
    pi.submit()


def make_material_request(item_code):
	mr = frappe.new_doc("Material Request")

	variant_of = frappe.db.get_value('Item', item_code, 'variant_of') or item_code

	if frappe.db.get_value('BOM', {'item': variant_of, 'is_default': 1, 'is_active': 1}):
		mr.material_request_type = 'Manufacture'
	else:
		mr.material_request_type = "Purchase"

	mr.transaction_date = frappe.flags.current_date
	mr.schedule_date = frappe.flags.current_date

	mr.append("items", {
		"doctype": "Material Request Item",
		"schedule_date": frappe.flags.current_date,
		"item_code": item_code,
		"qty": random.choice([250, 500, 750, 1000]),
        "warehouse": WAREHOUSE
	})
	mr.insert()
	mr.submit()
	return mr

def get_suppliers():
    for s in frappe.get_all("Supplier"):
        SUPPLIERS.append(s.name)
    