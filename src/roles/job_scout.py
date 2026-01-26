from .job_price import PriceSpy

class Radar:
    """
    THE RADAR (Scout)
    Role: Scans for top gainers or volume spikes.
    Currently reuses Spy's volume scan logic.
    """
    def __init__(self, spy_instance: Spy):
        self.spy = spy_instance

    def scan_market(self):
        """Finds interesting assets to trade (Top Volume for now)"""
        print("Radar: Scanning for targets...")
        return self.spy.get_top_symbols(limit=10)
