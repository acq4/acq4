from acq4.devices.OdorDelivery import OdorDelivery


class MockOdorDelivery(OdorDelivery):
    def setChannelValue(self, channel: int, value: int):
        print(f"setting {channel} to {value}")
