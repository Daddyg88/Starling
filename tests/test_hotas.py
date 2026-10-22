"""Any HOTAS works, not only the X52."""
import unittest

from control import inputs
from control.combat_assist import fire_specs
from control.inputs import ButtonReader, JoyDevice


def dev(name, buttons=32, vendor=1, product=2, index=0):
    return JoyDevice(index, vendor, product, name, buttons)


class DetectionTests(unittest.TestCase):
    def test_common_hotas_are_recognised(self):
        for name in ("Saitek X52 Pro Flight Control System", "Thrustmaster T.16000M", "HOTAS Warthog Joystick", "VKB Gladiator NXT EVO",
                     "Logitech Extreme 3D Pro", "VIRPIL Constellation Alpha", "Honeycomb Alpha Flight Controls", "T.Flight Hotas One"):
            self.assertTrue(dev(name).is_hotas(), name)

    def test_gamepads_and_virtual_devices_are_not(self):
        for name in ("Controller (Xbox One For Windows)", "vJoy Device", "Wireless Controller"):
            self.assertFalse(dev(name, buttons=11).is_hotas(), name)

    def test_throttles_and_pedals_are_not_the_stick(self):
        self.assertTrue(dev("HOTAS Warthog Joystick").is_stick())
        self.assertFalse(dev("HOTAS Warthog Throttle").is_stick())
        self.assertTrue(dev("HOTAS Warthog Throttle").is_hotas())
        self.assertFalse(dev("Saitek Pro Flight Rudder Pedals").is_stick())

    def test_elite_names_find_the_device(self):
        warthog = dev("HOTAS Warthog Joystick")
        self.assertTrue(warthog.matches_elite_name("ThrustMasterWarthogJoystick"))
        self.assertTrue(dev("Thrustmaster T.16000M").matches_elite_name("T16000M"))
        self.assertFalse(dev("VKB Gladiator NXT EVO").matches_elite_name("ThrustMasterWarthogJoystick"))


class FakeJoysticks:
    def __init__(self, devices):
        self._devices = devices

    def devices(self):
        return self._devices

    def buttons(self, index):
        return 0


class ReaderTests(unittest.TestCase):
    def test_reader_lists_sticks_and_all_hotas(self):
        stick, throttle, pad = dev("HOTAS Warthog Joystick", index=0), dev("HOTAS Warthog Throttle", index=1), dev("Xbox Controller", 11, index=2)
        reader = ButtonReader(keyboard=object(), joysticks=FakeJoysticks([stick, throttle, pad]))
        self.assertEqual(reader.stick_devices(), [stick])
        self.assertEqual(reader.hotas_devices(), [stick, throttle])
        self.assertEqual(reader.devices_named("ThrustMasterWarthogJoystick"), [stick])


class FireButtonTests(unittest.TestCase):
    def test_a_named_non_x52_stick_gives_fire_buttons(self):
        from control.binds import BindingBook, parse_binds

        class Book(BindingBook):
            def __init__(self):
                self._actions = parse_binds('<Root><PrimaryFire><Primary Device="ThrustMasterWarthogJoystick" Key="Joy_1"/>'
                                            '<Secondary Device="{NoDevice}" Key=""/></PrimaryFire></Root>')

            def refresh(self):
                return True
        stick = dev("HOTAS Warthog Joystick", vendor=0x044F, product=0x0402)
        reader = ButtonReader(keyboard=object(), joysticks=FakeJoysticks([stick]))
        self.assertEqual(fire_specs(Book(), reader), [inputs.joy_spec(stick, 1)])


if __name__ == "__main__":
    unittest.main()
