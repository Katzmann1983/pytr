from datetime import datetime
from collections import UserDict
import re
from .file_destination_provider import Pattern

tr_eventType_to_pp_type = {
    "CREDIT": "DIVIDENDS",
    "ssp_corporate_action_invoice_cash": "DIVIDENDS",
    "TRADE_INVOICE": "TRADE_INVOICE",
    "SAVINGS_PLAN_EXECUTED": "TRADE_INVOICE",
    "ORDER_EXECUTED": "TRADE_INVOICE",
    "PAYMENT_INBOUND": "DEPOSIT",
    "PAYMENT_INBOUND_SEPA_DIRECT_DEBIT": "DEPOSIT",
    "PAYMENT_OUTBOUND": "REMOVAL",
    "INTEREST_PAYOUT_CREATED": "INTEREST",
    "card_successful_transaction": "REMOVAL",
    "card_successful_atm_withdrawal": "REMOVAL",
    "card_order_billed": "REMOVAL",
    "card_refund": "DEPOSIT",
}

subfolder = {
        'benefits_saveback_execution': 'Saveback',
        'benefits_spare_change_execution': 'RoundUp',
        'ssp_corporate_action_invoice_cash': 'Dividende',
        'CREDIT': 'Dividende',
        'INTEREST_PAYOUT_CREATED': 'Zinsen',
        "SAVINGS_PLAN_EXECUTED":'Sparplan'
    }


class Document(UserDict, Pattern):
    def __init__(self, doc, event, section_title):
        super().__init__(doc)
        # initialize the Pattern attributes
        self.event_type = event.eventType
        self.event_subtitle = event.subtitle
        self.event_title = event.title
        self.section_title = section_title
        self.document_title = doc['title']
        try:
            timestamp = datetime.strptime(doc['detail'], '%d.%m.%Y').timestamp()
        except (ValueError, KeyError):
            timestamp = datetime.now().timestamp()
        self.timestamp = timestamp
        self.title = f"{doc['title']} - {event.title}"
        if event.pp_type in ["ACCOUNT_TRANSFER_INCOMING", "ACCOUNT_TRANSFER_OUTGOING", "CREDIT"]:
            self.title += f" - {event.subtitle}"
        self.event_subtitle = '' if event.subtitle is None else event.subtitle

        self.event_subfolder = event.subfolder
        self.determine_doctype()

    def determine_doctype(self):
        doc_type = self['title'].rsplit(' ')
        if doc_type[-1].isnumeric() is True:
            doc_type_num = f' {doc_type.pop()}'
        else:
            doc_type_num = ''

        self.doc_type = ' '.join(doc_type)
        self.doc_type_num = doc_type_num




class Event(UserDict):
    def __init__(self, event_json):
        super().__init__(event_json)
        self.shares = ""
        self.isin = ""
        self.eventType = self.get("eventType", "")

        self.subfolder = subfolder.get(self.eventType, "")
        self.pp_type = tr_eventType_to_pp_type.get(self.eventType, "")
        self.body = self.get("body", "")
        self.process_event()

    @property
    def date(self):
        dateTime = datetime.fromisoformat(self["timestamp"][:19])
        return dateTime.strftime("%Y-%m-%d")

    @property
    def is_pp_relevant(self):
        return self.pp_type != ""

    @property
    def amount(self):
        return str(self["amount"]["value"])

    @property
    def note(self):
        if self["eventType"].find("card_") == 0:
            return self["eventType"]
        else:
            return ""

    @property
    def title(self):
        return self.get("title", "")

    @property
    def subtitle(self):
        if self.eventType in ["ACCOUNT_TRANSFER_INCOMING", "ACCOUNT_TRANSFER_OUTGOING", "CREDIT"]:
            return self.get("subtitle", "")

    def determine_pp_type(self):
        if self.pp_type == "TRADE_INVOICE":
            if self["amount"]["value"] < 0:
                self.pp_type = "BUY"
            else:
                self.pp_type = "SELL"

    def determine_shares(self):
        if self.pp_type == "TRADE_INVOICE":
            sections = self.get("details", {}).get("sections", [{}])
            for section in sections:
                if section.get("title") == "Transaktion":
                    self.shares = section.get("data", [{}])[0]["detail"][
                        "text"
                    ].replace(",", ".")

    def determine_isin(self):
        if self.pp_type in ("DIVIDENDS", "TRADE_INVOICE"):
            sections = self.get("details", {}).get("sections", [{}])
            self.isin = self.get("icon", "")
            self.isin = self.isin[self.isin.find("/") + 1 :]
            self.isin = self.isin[: self.isin.find("/")]
            isin2 = self.isin
            for section in sections:
                action = section.get("action", None)
                if action and action.get("type", {}) == "instrumentDetail":
                    isin2 = section.get("action", {}).get("payload")
            if self.isin != isin2:
                self.isin = isin2

    def process_event(self):
        self.determine_shares()
        self.determine_isin()
        self.determine_pp_type()

    def set_details(self, details):
        self["details"] = details
        self.process_event()

    def get_documents(self, response):
        documents = []
        for section in response['sections']:
            if section['type'] != 'documents':
                continue
            for doc in section['data']:
                documents.append(Document(doc, self, section['title']))
        return documents