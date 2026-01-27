from .job_price import PriceSpy

class Radar:
    """
    THE RADAR (Scout)
    Role: Scans for top gainers or volume spikes.
    Currently reuses Spy's volume scan logic.
    """
    def __init__(self, spy_instance: PriceSpy):
        self.spy = spy_instance

    def scan_market(self, callback=None, logger=None):
        """Finds interesting assets to trade (Top Volume for now)"""
        print("Radar: Scanning for targets...")
        return self.spy.get_top_symbols(limit=limit if 'limit' in  locals() else 35, callback=callback, logger=logger)
