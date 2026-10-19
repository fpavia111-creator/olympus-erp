"""Initial migration templates: never treat these as official vendor schemas."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Field:
    kind: str = "text"
    required: bool = False
    minimum: str | None = None
    allowed: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    unique: bool = False
    related: tuple[str, str] | None = None

@dataclass(frozen=True)
class Template:
    label: str
    fields: dict[str, Field] = field(default_factory=dict)
    key: str = "External ID"
    duplicate_name: str = ""
    journal: tuple[str, str, str] | None = None

TEMPLATES = {
    "netsuite.customer": Template("NetSuite customers", {
        "External ID": Field(required=True, unique=True, aliases=("Customer ID", "Customer Number", "CustomerID", "ID")),
        "Company Name": Field(required=True, aliases=("Customer Name", "Company", "Name")),
        "Email": Field("email", aliases=("E-mail", "Email Address")),
        "State": Field("state", aliases=("Province", "State/Province")),
        "Country": Field("country", aliases=("Country Code",)),
        "Terms": Field(aliases=("Payment Terms",)),
        "Credit Limit": Field("number", minimum="0", aliases=("CreditLimit",)),
        "Subsidiary": Field(),
    }, duplicate_name="Company Name"),
    "netsuite.vendor": Template("NetSuite vendors", {
        "External ID": Field(required=True, unique=True, aliases=("Vendor ID", "Vendor Number", "Supplier ID")),
        "Company Name": Field(required=True, aliases=("Vendor Name", "Supplier Name", "Name")),
        "Email": Field("email", aliases=("E-mail", "Email Address")),
        "State": Field("state"), "Country": Field("country"), "Terms": Field(),
    }, duplicate_name="Company Name"),
    "netsuite.item": Template("NetSuite items", {
        "External ID": Field(required=True, unique=True, aliases=("Item ID", "Item Number", "SKU")),
        "Item Name": Field(required=True, aliases=("Name", "Item", "Product")),
        "Base Price": Field("number", minimum="0", aliases=("Price", "Sales Price")),
        "Item Type": Field(aliases=("Type",)),
    }, duplicate_name="Item Name"),
    "netsuite.open_invoice": Template("NetSuite open AR invoices", {
        "External ID": Field(required=True, unique=True, aliases=("Invoice Number", "Invoice No", "Invoice ID")),
        "Customer": Field(required=True, aliases=("Customer ID", "Customer Number"), related=("netsuite.customer", "External ID")),
        "Item": Field(aliases=("Item ID", "SKU"), related=("netsuite.item", "External ID")),
        "Date": Field("date", required=True, aliases=("Invoice Date", "Txn Date")),
        "Amount": Field("number", aliases=("Open Balance", "Balance", "Total")),
    }),
    "netsuite.open_ap_bill": Template("NetSuite open AP bills", {
        "External ID": Field(required=True, unique=True, aliases=("Bill Number", "Bill No", "Bill ID", "Ref Number")),
        "Vendor": Field(required=True, aliases=("Vendor ID", "Supplier ID"), related=("netsuite.vendor", "External ID")),
        "Item": Field(aliases=("Item ID", "SKU"), related=("netsuite.item", "External ID")),
        "Date": Field("date", required=True, aliases=("Bill Date", "Txn Date")),
        "Due Date": Field("date", aliases=("DueDate",)),
        "Amount": Field("number", aliases=("Open Balance", "Balance", "Total")),
    }),
    "netsuite.inventory_on_hand": Template("NetSuite inventory on hand", {
        "External ID": Field(required=True, unique=True, aliases=("Inventory ID", "Row ID", "Record ID")),
        "Item": Field(required=True, aliases=("Item ID", "SKU"), related=("netsuite.item", "External ID")),
        "Location": Field(required=True, aliases=("Warehouse", "Site")),
        "Quantity": Field("number", required=True, minimum="0", aliases=("Qty On Hand", "Qty", "On Hand")),
        "Unit Cost": Field("number", minimum="0", aliases=("Cost", "Average Cost")),
    }),
    "netsuite.journal": Template("NetSuite opening-balance journal", {
        "Journal ID": Field(required=True, aliases=("Journal", "Entry ID")),
        "Account": Field(required=True, aliases=("Account Number",)),
        "Debit": Field("number", minimum="0", aliases=("Debit Amount",)),
        "Credit": Field("number", minimum="0", aliases=("Credit Amount",)),
        "Date": Field("date", aliases=("Transaction Date",)),
        "Subsidiary": Field(),
    }, key="Journal ID", journal=("Journal ID", "Debit", "Credit")),
    "salesforce.account": Template("Salesforce accounts", {
        "External ID": Field(required=True, unique=True, aliases=("Account ID", "Account Number", "ID")),
        "Account Name": Field(required=True, aliases=("Name", "Company")),
        "Website": Field(), "Phone": Field(),
    }, duplicate_name="Account Name"),
    "salesforce.contact": Template("Salesforce contacts", {
        "External ID": Field(required=True, unique=True, aliases=("Contact ID", "ID")),
        "Last Name": Field(required=True, aliases=("Surname", "LastName")),
        "First Name": Field(aliases=("Given Name", "FirstName")),
        "Email": Field("email", aliases=("Email Address", "E-mail")),
        "Account External ID": Field(aliases=("Account ID", "Company ID"), related=("salesforce.account", "External ID")),
    }),
    "salesforce.opportunity": Template("Salesforce opportunities", {
        "External ID": Field(required=True, unique=True, aliases=("Opportunity ID", "ID")),
        "Name": Field(required=True, aliases=("Opportunity Name", "Deal Name")),
        "Account External ID": Field(required=True, aliases=("Account ID",), related=("salesforce.account", "External ID")),
        "Stage": Field(required=True, aliases=("Stage Name", "Pipeline Stage")),
        "Close Date": Field("date", required=True, aliases=("Expected Close", "CloseDate")),
        "Amount": Field("number", minimum="0", aliases=("Value", "Deal Value")),
    }),
    "workday.worker": Template("Workday workers (EIB starting point)", {
        "Worker ID": Field(required=True, unique=True, aliases=("Employee ID", "Person ID")),
        "First Name": Field(required=True, aliases=("Given Name",)),
        "Last Name": Field(required=True, aliases=("Surname",)),
        "Email": Field("email", aliases=("Work Email",)),
        "Manager ID": Field(aliases=("Supervisor ID",), related=("workday.worker", "Worker ID")),
        "Hire Date": Field("date", aliases=("Start Date",)),
    }, key="Worker ID"),
}

# Explicit source vocabulary for guarded automatic column matching.
PRESETS = {
    "quickbooks": {"Customer Name": "Company Name", "Customer ID": "External ID", "Txn Date": "Date",
                   "Invoice No": "External ID", "Invoice Number": "External ID", "Item Number": "External ID",
                   "Vendor Name": "Company Name", "Vendor ID": "External ID", "Open Balance": "Amount"},
    "sage": {"CustomerCode": "External ID", "CustomerName": "Company Name", "VendorCode": "External ID",
             "VendorName": "Company Name", "DocumentNo": "External ID", "DocumentDate": "Date",
             "StockCode": "External ID", "Description": "Item Name"},
}

def describe(name: str) -> dict:
    t = TEMPLATES[name]
    return {"name": name, "label": t.label, "fields": {
        n: {"type": f.kind, "required": f.required, "unique": f.unique, "minimum": f.minimum,
            "allowed": list(f.allowed), "aliases": list(f.aliases), "related": list(f.related) if f.related else None}
        for n, f in t.fields.items()}}
