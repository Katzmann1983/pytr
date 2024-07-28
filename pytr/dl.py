import re
import json

from concurrent.futures import as_completed
from pathlib import Path
from requests_futures.sessions import FuturesSession
from requests import session

from pathvalidate import sanitize_filepath

from pytr.utils import preview, get_logger
from pytr.api import TradeRepublicError
from pytr.timeline import Timeline
from .event import Document
from .transactions import export_transactions
from pytr.file_destination_provider import FileDestinationProvider

fdp = FileDestinationProvider()

class DL:
    def __init__(
        self,
        tr,
        output_path,
        filename_fmt,
        since_timestamp=0,
        history_file='pytr_history',
        max_workers=8,
        universal_filepath=False,
    ):
        '''
        tr: api object
        output_path: name of the directory where the downloaded files are saved
        filename_fmt: format string to customize the file names
        since_timestamp: downloaded files since this date (unix timestamp)
        '''
        self.tr = tr
        self.output_path = Path(output_path)
        self.history_file = self.output_path / history_file
        self.filename_fmt = filename_fmt
        self.since_timestamp = since_timestamp
        self.universal_filepath = universal_filepath

        requests_session = session()
        if self.tr._weblogin:
            requests_session.headers = self.tr._default_headers_web
        else:
            requests_session.headers = self.tr._default_headers
        self.session = FuturesSession(max_workers=max_workers, session=requests_session)
        self.futures = []

        self.docs_request = 0
        self.done = 0
        self.filepaths = []
        self.doc_urls = []
        self.doc_urls_history = []
        self.tl = Timeline(self.tr, self.since_timestamp)
        self.log = get_logger(__name__)
        self.load_history()

    def load_history(self):
        '''
        Read history file with URLs if it exists, otherwise create empty file
        '''
        if self.history_file.exists():
            with self.history_file.open() as f:
                self.doc_urls_history = f.read().splitlines()
            self.log.info(f'Found {len(self.doc_urls_history)} lines in history file')
        else:
            self.history_file.parent.mkdir(exist_ok=True, parents=True)
            self.history_file.touch()
            self.log.info('Created history file')

    async def dl_loop(self):
        await self.tl.get_next_timeline_transactions()
        while True:
            try:
                _, subscription, response = await self.tr.recv()
                if subscription['type'] == 'timelineTransactions':
                    await self.tl.get_next_timeline_transactions(response)
                elif subscription['type'] == 'timelineActivityLog':
                    await self.tl.get_next_timeline_activity_log(response)
                elif subscription['type'] == 'timelineDetailV2':
                    await self.tl.process_timelineDetail(response, self)
                    if self.tl.received_detail == self.tl.requested_detail:
                        break
                else:
                    self.log.warning(f"unmatched subscription of type '{subscription['type']}':\n{preview(response)}")
            except TradeRepublicError as e:
                self.log.fatal(str(e))
        
        self.log.info('Received all details')        
        self.output_path.mkdir(parents=True, exist_ok=True)
        with open(self.output_path / 'other_events.json', 'w', encoding='utf-8') as f:
            json.dump(self.tl.events_without_docs, f, ensure_ascii=False, indent=2)

        with open(self.output_path / 'events_with_documents.json', 'w', encoding='utf-8') as f:
            json.dump(self.tl.events_with_docs, f, ensure_ascii=False, indent=2)

        with open(self.output_path / 'all_events.json', 'w', encoding='utf-8') as f:
            json.dump(self.tl.events_without_docs + self.tl.events_with_docs, f, ensure_ascii=False, indent=2)
        export_transactions(self.output_path / 'all_events.json', self.output_path / 'account_transactions.csv')
        self.work_responses()

    def dl_doc(self, doc: Document):
        '''
        send asynchronous request, append future with filepath to self.futures
        '''

        doc_url = doc['action']['payload']
        
        filepath = self.output_path / fdp.get_file_path(doc)

        if self.universal_filepath:
            filepath = sanitize_filepath(filepath, '_', 'universal')
        else:
            filepath = sanitize_filepath(filepath, '_', 'auto')

        def add_doc_id(filepath, filename, doc_id):
            filepath = str(filepath)
            start = filepath[:filepath.find(filename)]
            end = filepath[filepath.find(filename)+len(filename):]
            filepath = start + f"{filename}_{doc_id}" + end
            return Path(filepath)

        if filepath in self.filepaths:
            self.log.debug(f"File {filepath} already in queue. Append document id {doc['id']}...")
            filepath_with_doc_id = add_doc_id(filepath, filename, doc['id'])
            if filepath_with_doc_id in self.filepaths:
                self.log.debug(f'File {filepath_with_doc_id} already in queue. Skipping...')
                return
            else:
                filepath = filepath_with_doc_id
        doc['local filepath'] = str(filepath)
        self.filepaths.append(filepath)

        if not filepath.is_file():
            doc_url_base = doc_url.split('?')[0]
            if doc_url_base in self.doc_urls:
                self.log.debug(f'URL {doc_url_base} already in queue. Skipping...')
                return
            elif doc_url_base in self.doc_urls_history:
                self.log.debug(f'URL {doc_url_base} already in history. Skipping...')
                return
            else:
                self.doc_urls.append(doc_url_base)

            future = self.session.get(doc_url)
            future.filepath = filepath
            future.doc_url_base = doc_url_base
            self.futures.append(future)
            self.log.debug(f'Added {filepath} to queue')
        else:
            self.log.debug(f'file {filepath} already exists. Skipping...')

    def work_responses(self):
        '''
        process responses of async requests
        '''
        if len(self.doc_urls) == 0:
            self.log.info('Nothing to download')
            exit(0)

        with self.history_file.open('a') as history_file:
            self.log.info('Waiting for downloads to complete..')
            for future in as_completed(self.futures):
                if future.filepath.is_file() is True:
                    self.log.debug(f'file {future.filepath} was already downloaded.')

                try:
                    r = future.result()
                except Exception as e:
                    self.log.fatal(str(e))

                future.filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(future.filepath, 'wb') as f:
                    f.write(r.content)
                    self.done += 1
                    history_file.write(f'{future.doc_url_base}\n')

                    self.log.debug(f'{self.done:>3}/{len(self.doc_urls)} {future.filepath.name}')

                if self.done == len(self.doc_urls):
                    self.log.info('Done.')
                    exit(0)
