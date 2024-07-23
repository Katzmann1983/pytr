from datetime import datetime
from collections import UserDict
import re

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


class Document(UserDict):
    def __init__(self, doc, event):
        super().__init__(doc)
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


    def get_filename(self, filename_fmt):
        try:
            date = self['detail']
            iso_date = '-'.join(date.split('.')[::-1])
        except KeyError:
            date = ''
            iso_date = ''
        doc_id = self['id']

        # extract time from subtitleText
        try:
            time = re.findall('um (\\d+:\\d+) Uhr', self.event_subtitle)
            if time == []:
                time = ''
            else:
                time = f' {time[0]}'
        except TypeError:
            time = ''

        titleText = self.title.replace('\n', '').replace('/', '-')
        subtitleText = self.event_subtitle.replace('\n', '').replace('/', '-')

        filename = filename_fmt.format(
            iso_date=iso_date, time=time, title=titleText, subtitle=subtitleText, doc_num=self.doc_type_num, id=doc_id
        )
        return filename

    def get_filepath(self, output_path, filename_fmt):
        filename = self.get_filename(filename_fmt)
        if self.event_subfolder is not None:
            directory = output_path / self.event_subfolder
        else:
            directory = output_path

        if self.doc_type in ['Kontoauszug', 'Depotauszug']:
            filepath = directory / 'Abschlüsse' / f'{filename}' / f'{self.doc_type}.pdf'
        else:
            filepath = directory / self.doc_type / f'{filename}.pdf'
        return filepath


class Event(UserDict):
    def __init__(self, event_json):
        super().__init__(event_json)
        self.json = event_json
        self.shares = ""
        self.isin = ""
        self.eventType = self.json.get("eventType", "")

        self.subfolder = subfolder.get(self.eventType, "")
        self.pp_type = tr_eventType_to_pp_type.get(self.eventType, "")
        self.body = self.json.get("body", "")
        self.process_event()

    @property
    def date(self):
        dateTime = datetime.fromisoformat(self.json["timestamp"][:19])
        return dateTime.strftime("%Y-%m-%d")

    @property
    def is_pp_relevant(self):
        return self.pp_type != ""

    @property
    def amount(self):
        return str(self.json["amount"]["value"])

    @property
    def note(self):
        if self.json["eventType"].find("card_") == 0:
            return self.json["eventType"]
        else:
            return ""

    @property
    def title(self):
        return self.json.get("title", "")

    @property
    def subtitle(self):
        if self.eventType in ["ACCOUNT_TRANSFER_INCOMING", "ACCOUNT_TRANSFER_OUTGOING", "CREDIT"]:
            return self.json.get("subtitle", "")

    def determine_pp_type(self):
        if self.pp_type == "TRADE_INVOICE":
            if self.json["amount"]["value"] < 0:
                self.pp_type = "BUY"
            else:
                self.pp_type = "SELL"

    def determine_shares(self):
        if self.pp_type == "TRADE_INVOICE":
            sections = self.json.get("details", {}).get("sections", [{}])
            for section in sections:
                if section.get("title") == "Transaktion":
                    self.shares = section.get("data", [{}])[0]["detail"][
                        "text"
                    ].replace(",", ".")

    def determine_isin(self):
        if self.pp_type in ("DIVIDENDS", "TRADE_INVOICE"):
            sections = self.json.get("details", {}).get("sections", [{}])
            self.isin = self.json.get("icon", "")
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
        self.json["details"] = details
        self.process_event()

    def get_documents(self, response):
        documents = []
        for section in response['sections']:
            if section['type'] != 'documents':
                continue
            for doc in section['data']:
                documents.append(Document(doc, self))
        return documents