from array import array
import math
import unittest
from penasmr.core import Tracker, Friction, Motion

class Tests(unittest.TestCase):
    def test_hover_and_first_contact_do_not_sound(self):
        t=Tracker()
        t.update(0,0,0,False,1)
        t.update(.1,0,.5,True,1.01)
        self.assertEqual(t.motion.speed,0)
        t.update(.11,0,.5,True,1.02)
        self.assertAlmostEqual(t.motion.speed,1)
        t.update(.2,0,0,False,1.03)
        self.assertEqual(t.motion.pressure,0)

    def test_stationary_and_stale_stop(self):
        e=Friction()
        m=Motion(.3,.6,1)
        self.assertTrue(any(array('f',e.render(1024,m,1.001))))
        e.render(1024,m,1.1) # release ramp prevents click
        self.assertFalse(any(array('f',e.render(1024,m,1.1))))
        self.assertFalse(any(array('f',e.render(1024,Motion(0,.6,2),2))))

    def test_distance_controls_texture_and_pressure_controls_energy(self):
        def render(speed,pressure):
            e=Friction(); e.rng.seed(2)
            data=array('f',e.render(4800,Motion(speed,pressure,1),1))
            return e.phase,sum(v*v for v in data)
        slow,_=render(.1,.5)
        fast,_=render(.2,.5)
        self.assertAlmostEqual(fast,2*slow)
        e=Friction(); e.rng.seed(3)
        a=array('f',e.render(4800,Motion(.2,.1,1),1))
        e.gain=e.phase=e.low=0; e.rng.seed(3)
        b=array('f',e.render(4800,Motion(.2,1,1),1))
        self.assertGreater(sum(v*v for v in b),sum(v*v for v in a)*2)

    def test_muting_and_finite_bounded_output(self):
        e=Friction()
        data=array('f',e.render(5000,Motion(8,1,1),1))
        self.assertTrue(all(math.isfinite(v) and abs(v)<=.95 for v in data))
        e.enabled=False
        e.render(1024,Motion(1,1,1),1)
        self.assertFalse(any(array('f',e.render(512,Motion(1,1,1),1))))

if __name__=='__main__': unittest.main()
