import errno
import os
import os.path
import datetime


class DataManager(object):

    DATE_FORMAT = '%Y-%m-%d'

    """A DataManager is responsible for managing (i.e. storing and
    retrieving) data on disk.

    In other words, this class provides an interface by which stock
    data can be queried from or stored onto disk. With regards to
    functions found in this class, 'public' functions house high level
    logic for publicly used actions, while 'private' functions act as
    wrappers for low level or commonly used and simple, but ugly to
    write actions.

    Attributes:
        data_location: A string indicating where the stock data is
            stored on disk

    Todo:
        - [code improvement, low priority] create independent market
            open reference dates
        - [code improvement, low priority] implement reading csv rows
            to return map
        - [code improvement, low priority] implement reading csv
            columns to return map
    """

    def __init__(self, data_location='data/'):
        """Inits DataManager with a data location.

        Args:
            data_location: (optional) A string representing where the
                data dir will be on disk, default: ./data/
        """
        self.data_location = data_location
        os.makedirs(self.data_location, exist_ok=True)

    def write_stock_data(self, ticker, data, append):
        """Writes an array of data to a file on disk.

        Args:
            ticker: A string representing the ticker of a stock
            data: An array in [[date,open,high,low,close,volume],...]
                format
            append: A boolean representing whether or not to append to
                existing data
        """
        data_to_write = []
        if append:
            mode = 'a'
            existing_data = self.read_stock_data(ticker, 'row')
            if len(existing_data) == 0:
                data_to_write = data
            elif (existing_data[-1][0] < data[-1][0] and
                  existing_data[-1][0] > data[0][0]):
                index_of_last = next(i for i, _ in enumerate(data)
                                     if _[0] == existing_data[-1][0])
                data_to_write = data[index_of_last + 1:]
        else:
            mode = 'w'
            data_to_write = data
            if self._has_file_for(ticker):
                self._remove_file_for(ticker)
        self._write_data_to_csv_file(
            self._filename_for(ticker), data_to_write, mode)

    def read_stock_data(self, ticker, format):
        """Retrieves stock data for a given ticker in a given format
        from disk.

        Args:
            ticker: A string representing the ticker of a stock
            format: A string representing whether the data should be in
                'column' or 'row' format

        Returns:
            An array in either row or column format contaning the data
                for a given stock
        """
        if format == 'column':
            return self._read_csv_file_columns_for(ticker)
        if format == 'row':
            return self._read_csv_file_rows_for(ticker)
        return []

    def build_price_lut(self, ticker, fill=True):
        """Builds a price look up table for a given ticker.

        Args:
            ticker: A string representing the ticker of a stock
            fill: Whether or not to fill holidays/weekends with
                previous data
                NOTE: experimental feature which made some slightly
                unexpected numbers come up - turned off for now

        Returns:
            A dictionary with dates as keys and prices as values
        """
        price_lookup = {}
        file_content = self._readlines_for(ticker)
        # handle corner cases with empty or single-line files
        if len(file_content) == 0:
            return price_lookup
        if len(file_content) == 1:
            line_data = file_content[i].split(',')
            return {line_data[0]: float(line_data[4])}
        # handle multi-line files & fill in holes with previous data
        for i in range(0, len(file_content) - 1):
            curr_line_data = file_content[i].split(',')
            next_line_data = file_content[i + 1].split(',')
            curr_date = datetime.datetime.strptime(
                curr_line_data[0], DataManager.DATE_FORMAT)
            next_date = datetime.datetime.strptime(
                next_line_data[0], DataManager.DATE_FORMAT)
            while curr_date < next_date:
                price_lookup[curr_date.strftime(DataManager.DATE_FORMAT)] \
                    = float(curr_line_data[4])
                if fill:
                    curr_date = curr_date + datetime.timedelta(1)
                else:
                    curr_date = next_date
        # handle last line in file separately
        price_lookup[next_date.strftime(
            DataManager.DATE_FORMAT)] = float(next_line_data[4])
        return price_lookup

    def build_strategy(self, strategy_name, strategy_dir='./'):
        """Given a strategy name (the name of the file within which
        the strategy is coded) and builds the data structure for Brain
        to use, then returns the structure along with all assets and
        indicators needed in the Market.

        Args:
            strategy_name: A name for the strategy to use - corresponds
                to a file in the strategies dir
            strategy_dir: An optional value containing a custom
                location for strategies (default: ./)

        Returns:
            A tuple containing the strategy structure, a set of assets
            to add to the Market, and a set of indicators to add to the
            Market
        """
        lines = self._readlines(strategy_dir + strategy_name)
        stocks_needed = set({})
        indicators_needed = set({})
        strategy = {
            'assets': set({}),
            'positions': []
        }
        for line in lines:
            (ratio, ticker, buy_signal, sell_signal) = line.split(',')
            strategy['assets'].add(ticker.upper())
            stocks_needed.add(ticker.upper())
            for signal in [buy_signal, sell_signal]:
                (tickers, indicators) = self._parse_signal(signal)
                stocks_needed |= tickers
                indicators_needed |= indicators
            strategy['positions'].append({
                'is_holding': False,
                'ratio': float(ratio),
                'ticker': ticker.upper(),
                'buy_signal': buy_signal,
                'sell_signal': sell_signal
            })
        return (strategy, stocks_needed, indicators_needed)

    def _parse_signal(self, signal_code):
        """Parses a buy or sell signal and extracts any tickers and
        indicators from it.

        Args:
            signal_code: A code for a buy or sell signal

        Returns:
            A tuple containing a set of tickers and a set of indicators
        """
        if signal_code in ['ALWAYS', 'NEVER']:
            return (set({}), set({}))
        tickers = set({})
        indicators = set({})
        (val_a_code, _, val_b_code) = signal_code.split(' ')
        for code in [val_a_code, val_b_code]:
            (ticker, indicator) = code.split('~')
            tickers.add(ticker.upper())
            if indicator not in ['PRICE']:
                indicators.add(indicator.upper())
        return (tickers, indicators)

    def _write_data_to_csv_file(self, filename, data, mode):
        """Writes an array of data to disk in CSV format.

        Args:
            filename: A string representing the file to which to write
            data: An array in [[date,open,high,low,close,volume],...]
                format
        """
        with open(filename, mode) as file:
            for line in data:
                file.write(','.join(line) + '\n')

    def _filename_for(self, ticker):
        """Returns the file name for a ticker, including the path to
        said file.

        Args:
            ticker: A string representing the ticker of a stock

        Returns:
            A String representing the filename, inluding path, for the
            given ticker
        """
        return self.data_location + ticker.upper() + ".csv"

    def _readlines(self, filename):
        """Returns the lines of the file for a given ticker.

        Args:
            filename: A string representing the name of a file

        Returns:
            An array with each element containing a line of the file
        """
        lines = []
        if self._has_file(filename):
            with open(filename, 'r') as file:
                lines = [line.strip() for line in file]
        return lines

    def _readlines_for(self, ticker):
        """Returns the lines of the file for a given ticker.

        Args:
            ticker: A string representing the ticker of a stock

        Returns:
            An array with each element containing a line of the file
            for the given ticker
        """
        lines = []
        if self._has_file_for(ticker):
            with open(self._filename_for(ticker), 'r') as file:
                lines = [line.strip() for line in file]
        return lines

    def _has_file(self, filename):
        """Returns whether a file exists.

        Args:
            filename: A string representing the filename

        Returns:
            A boolean value representing whether or not the file exists
        """
        return os.path.isfile(filename)

    def _has_file_for(self, ticker):
        """Returns whether a file for a given ticker exists.

        Args:
            ticker: A string representing the ticker of a stock

        Returns:
            A boolean value representing whether or not a file exists
            for a given ticker
        """
        return os.path.isfile(self._filename_for(ticker))

    def _remove_file_for(self, ticker):
        """Removes the file for the given ticker.

        Args:
            ticker: A string representing the ticker of a stock
        """
        os.remove(self._filename_for(ticker))

    def _read_csv_file_rows_for(self, ticker):
        """Reads and returns the data in a CSV file for a given ticker
        in row-by-row format.

        Args:
            ticker: A string representing the ticker of a stock

        Returns:
            An array, where each element is an array containing data
            for a row in a CSV file
        """
        data = []
        file_content = self._readlines_for(ticker)
        for line in file_content:
            data.append([value.strip() for value in line.split(',')])
        return data

    def _read_csv_file_columns_for(self, ticker):
        """Reads and returns the data in a CSV file for a given ticker
        in column-by-column format.

        Args:
            ticker: A string representing the ticker of a stock

        Returns:
            An array, where each element is an array containing data
            for a column in a CSV file
        """
        data = []
        file_content = self._readlines_for(ticker)
        # create arrays for each column
        for i in range(0, 6):
            data.append([])
        # iterate through file
        for line in file_content:
            values = line.split(',')
            for i in range(0, 6):
                data[i].append(values[i].strip())
        return data
