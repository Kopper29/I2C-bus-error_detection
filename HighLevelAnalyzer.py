# High Level Analyzer - I2C Bus Error Detector
# Flags bus errors where SDA changes while SCL is high, causing
# unfinished/premature transaction termination.

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, ChoicesSetting


class Hla(HighLevelAnalyzer):

    show_mode = ChoicesSetting(
        label='Display',
        choices=('Errors only', 'Errors and warnings', 'All frames')
    )

    result_types = {
        'bus_error': {
            'format': 'BUS ERROR: {{data.error}}'
        },
        'start_marker': {
            'format': 'FAIL START: {{data.detail}}'
        },
        'warning': {
            'format': 'WARNING: {{data.warning}}'
        },
        'info': {
            'format': '{{data.info}}'
        },
    }

    # Transaction states
    IDLE = 'idle'
    STARTED = 'started'        # After START, expecting address
    ADDRESSED = 'addressed'    # After address, expecting data or stop
    DATA_PHASE = 'data_phase'  # Receiving/sending data bytes

    def __init__(self):
        self.state = self.IDLE
        self.transaction_start_time = None
        self.transaction_start_end_time = None
        self.prev_start_time = None
        self.prev_start_end_time = None
        self.last_frame_end = None
        self.address = None
        self.direction = None
        self.byte_count = 0

    def _addr_str(self):
        if self.address is not None:
            return '0x{:02X} {}'.format(self.address, self.direction or '?')
        return '?'

    def _make_start_marker(self, detail):
        """Create a frame highlighting the START of the failing transaction.
        Falls back to the previous transaction's START when no current one exists."""
        start = self.transaction_start_time or self.prev_start_time
        end = self.transaction_start_end_time or self.prev_start_end_time
        if start is not None:
            return AnalyzerFrame('start_marker',
                                 start,
                                 end or start,
                                 {'detail': detail})
        return None

    def _make_error(self, start, end, msg):
        return AnalyzerFrame('bus_error', start, end, {'error': msg})

    def _make_warning(self, start, end, msg):
        if self.show_mode in ('Errors and warnings', 'All frames'):
            return AnalyzerFrame('warning', start, end, {'warning': msg})
        return None

    def _make_info(self, start, end, msg):
        if self.show_mode == 'All frames':
            return AnalyzerFrame('info', start, end, {'info': msg})
        return None

    def decode(self, frame: AnalyzerFrame):
        results = []

        if frame.type == 'start':
            if self.state == self.STARTED:
                # Two STARTs with no address in between — SDA toggled while SCL high
                marker = self._make_start_marker(
                    'START of failed transaction (no address sent)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    self.transaction_start_time, frame.end_time,
                    'Repeated START with no address — SDA changed while SCL high'))

            elif self.state in (self.ADDRESSED, self.DATA_PHASE):
                # START while a transaction is in progress.
                # Repeated-start is legal in I2C, but flag incomplete
                # transactions that had no data transferred.
                if self.state == self.ADDRESSED and self.byte_count == 0:
                    marker = self._make_start_marker(
                        'START of aborted transaction ({})'.format(self._addr_str()))
                    if marker:
                        results.append(marker)
                    results.append(self._make_error(
                        self.transaction_start_time, frame.end_time,
                        'Transaction aborted (addr {}) — '
                        'START before any data transferred, '
                        'SDA changed while SCL high'.format(self._addr_str())))
                else:
                    w = self._make_warning(
                        self.transaction_start_time, frame.start_time,
                        'Repeated START during {} ({} bytes) — '
                        'verify this is intentional'.format(
                            self._addr_str(), self.byte_count))
                    if w:
                        results.append(w)

            self.state = self.STARTED
            self.prev_start_time = self.transaction_start_time
            self.prev_start_end_time = self.transaction_start_end_time
            self.transaction_start_time = frame.start_time
            self.transaction_start_end_time = frame.end_time
            self.byte_count = 0
            self.address = None
            self.direction = None

        elif frame.type == 'stop':
            if self.state == self.IDLE:
                # STOP with no active transaction — spurious SDA rising edge
                marker = self._make_start_marker(
                    'Previous START (no active transaction for this STOP)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    frame.start_time, frame.end_time,
                    'Unexpected STOP (no active transaction) — '
                    'SDA rose while SCL high'))

            elif self.state == self.STARTED:
                # START then immediate STOP, no address sent
                marker = self._make_start_marker(
                    'START of failed transaction (no address sent)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    self.transaction_start_time, frame.end_time,
                    'START immediately followed by STOP — '
                    'no address/data transferred'))

            elif self.state == self.ADDRESSED and self.byte_count == 0:
                # Addressed but no data before STOP
                marker = self._make_start_marker(
                    'START of failed transaction ({})'.format(self._addr_str()))
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    self.transaction_start_time, frame.end_time,
                    'Transaction to {} ended with no data bytes — '
                    'premature STOP'.format(self._addr_str())))
            else:
                i = self._make_info(
                    self.transaction_start_time, frame.end_time,
                    'OK {} — {} byte(s)'.format(
                        self._addr_str(), self.byte_count))
                if i:
                    results.append(i)

            self.state = self.IDLE
            self.prev_start_time = self.transaction_start_time
            self.prev_start_end_time = self.transaction_start_end_time
            self.transaction_start_time = None
            self.transaction_start_end_time = None
            self.byte_count = 0
            self.address = None
            self.direction = None

        elif frame.type == 'address':
            if self.state == self.IDLE:
                # Address byte without a START condition — bus error
                marker = self._make_start_marker(
                    'Previous START (missing START for this address byte)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    frame.start_time, frame.end_time,
                    'Address byte without preceding START — bus error'))

            # Extract address and direction
            raw_addr = frame.data.get('address', None)
            if isinstance(raw_addr, (list, bytes, bytearray)):
                self.address = raw_addr[0]
            elif isinstance(raw_addr, int):
                self.address = raw_addr
            else:
                self.address = None

            read_flag = frame.data.get('read', False)
            self.direction = 'Read' if read_flag else 'Write'

            ack = frame.data.get('ack', None)
            if ack is False:
                w = self._make_warning(
                    frame.start_time, frame.end_time,
                    'NACK on address {} — device not responding'.format(
                        self._addr_str()))
                if w:
                    results.append(w)

            self.state = self.ADDRESSED
            self.byte_count = 0

        elif frame.type == 'data':
            if self.state == self.IDLE:
                marker = self._make_start_marker(
                    'Previous START (missing START for this data byte)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    frame.start_time, frame.end_time,
                    'Data byte outside of transaction — '
                    'SDA changed while SCL high'))
            elif self.state == self.STARTED:
                marker = self._make_start_marker(
                    'START of transaction (data without address phase)')
                if marker:
                    results.append(marker)
                results.append(self._make_error(
                    frame.start_time, frame.end_time,
                    'Data byte without address phase — bus error'))

            self.byte_count += 1

            ack = frame.data.get('ack', None)
            if ack is False:
                w = self._make_warning(
                    frame.start_time, frame.end_time,
                    'NACK on data byte {} ({})'.format(
                        self.byte_count, self._addr_str()))
                if w:
                    results.append(w)

            self.state = self.DATA_PHASE

        elif frame.type == 'error':
            # The low-level I2C analyzer itself flagged an error
            marker = self._make_start_marker(
                'START of failed transaction ({})'.format(self._addr_str()))
            if marker:
                results.append(marker)
            results.append(self._make_error(
                frame.start_time, frame.end_time,
                'I2C analyzer error — SDA changed while SCL high '
                '(incomplete {} transaction)'.format(self._addr_str())))
            self.state = self.IDLE
            self.prev_start_time = self.transaction_start_time
            self.prev_start_end_time = self.transaction_start_end_time
            self.transaction_start_time = None
            self.transaction_start_end_time = None
            self.byte_count = 0

        self.last_frame_end = frame.end_time

        # Filter out None entries
        results = [r for r in results if r is not None]
        if len(results) == 1:
            return results[0]
        elif len(results) > 1:
            return results
        return None
