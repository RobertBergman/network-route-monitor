"""
Test suite for diffing.py - RIB and BGP diff algorithms
"""

import pytest
from diffing import rib_diff, bgp_diff
from models import RIBEntry, BGPEntry, NH, AFI4, set_hash

class TestRIBDiff:
    def test_rib_ecmp_change(self):
        """Test ECMP nexthop set changes"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1","Eth1/1")}
        )]
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1","Eth1/1"), NH("2.2.2.2","Eth1/2")}
        )]
        d = rib_diff(prev, curr)
        assert len(d["adds"]) == 0
        assert len(d["rems"]) == 0
        assert len(d["chgs"]) == 1
        assert "nexthops" in d["chgs"][0]["delta"]
        
        # Check that nexthops changed from 1 to 2
        old_nh, new_nh = d["chgs"][0]["delta"]["nexthops"]
        assert len(old_nh) == 1
        assert len(new_nh) == 2
    
    def test_rib_route_add(self):
        """Test new route addition"""
        prev = []
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="static", distance=1, metric=0, best=True,
            nexthops={NH("1.1.1.1", None)}
        )]
        d = rib_diff(prev, curr)
        assert len(d["adds"]) == 1
        assert len(d["rems"]) == 0
        assert len(d["chgs"]) == 0
        assert d["adds"][0]["prefix"] == "10.0.0.0/24"
    
    def test_rib_route_remove(self):
        """Test route removal"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="static", distance=1, metric=0, best=True,
            nexthops={NH("1.1.1.1", None)}
        )]
        curr = []
        d = rib_diff(prev, curr)
        assert len(d["adds"]) == 0
        assert len(d["rems"]) == 1
        assert len(d["chgs"]) == 0
        assert d["rems"][0]["prefix"] == "10.0.0.0/24"
    
    def test_rib_distance_change(self):
        """Test administrative distance change"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=90, metric=20, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        d = rib_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "distance" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["distance"] == (110, 90)
    
    def test_rib_metric_change(self):
        """Test metric change"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=30, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        d = rib_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "metric" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["metric"] == (20, 30)
    
    def test_rib_best_flag_change(self):
        """Test best route flag change"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="bgp", distance=200, metric=None, best=False,
            nexthops={NH("1.1.1.1", None)}
        )]
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="bgp", distance=200, metric=None, best=True,
            nexthops={NH("1.1.1.1", None)}
        )]
        d = rib_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "best" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["best"] == (False, True)
    
    def test_rib_no_change(self):
        """Test identical routes produce no diff"""
        prev = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        curr = [RIBEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/24",
            protocol="ospf", distance=110, metric=20, best=True,
            nexthops={NH("1.1.1.1", "Eth0")}
        )]
        d = rib_diff(prev, curr)
        assert len(d["adds"]) == 0
        assert len(d["rems"]) == 0
        assert len(d["chgs"]) == 0

class TestBGPDiff:
    def test_bgp_upstream_as_change(self):
        """Test upstream AS (first AS in path) change detection"""
        a = BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="0.0.0.0/0", best=True,
            nh="3.3.3.3", as_path="65001 3356", local_pref=100, med=0,
            origin="i", communities=[], communities_hash="h", weight=None, peer="1.1.1.1"
        )
        b = BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="0.0.0.0/0", best=True,
            nh="4.4.4.4", as_path="65002 3356", local_pref=100, med=0,
            origin="i", communities=[], communities_hash="h", weight=None, peer="2.2.2.2"
        )
        d = bgp_diff([a], [b])
        assert len(d["chgs"]) == 1
        assert "upstream_as" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["upstream_as"] == ("65001", "65002")
    
    def test_bgp_bestpath_flip(self):
        """Test best path selection change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=False,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "best" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["best"] == (False, True)
    
    def test_bgp_nexthop_change(self):
        """Test BGP nexthop change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="2.2.2.2", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "nh" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["nh"] == ("1.1.1.1", "2.2.2.2")
    
    def test_bgp_as_path_change(self):
        """Test AS path change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001 65002", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001 65003 65002", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "as_path" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["as_path"] == ("65001 65002", "65001 65003 65002")
    
    def test_bgp_local_pref_change(self):
        """Test local preference change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=200, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "local_pref" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["local_pref"] == (100, 200)
    
    def test_bgp_med_change(self):
        """Test MED change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=100,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "med" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["med"] == (50, 100)
    
    def test_bgp_communities_change(self):
        """Test communities change via hash"""
        comms1 = ["65001:100", "65002:200"]
        comms2 = ["65001:100", "65002:200", "65003:300"]
        
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=comms1, communities_hash=set_hash(comms1),
            weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=comms2, communities_hash=set_hash(comms2),
            weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "communities_hash" in d["chgs"][0]["delta"]
    
    def test_bgp_peer_change(self):
        """Test BGP peer change"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="2.2.2.2"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["chgs"]) == 1
        assert "peer" in d["chgs"][0]["delta"]
        assert d["chgs"][0]["delta"]["peer"] == ("1.1.1.1", "2.2.2.2")
    
    def test_bgp_route_add(self):
        """Test new BGP route"""
        prev = []
        curr = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        d = bgp_diff(prev, curr)
        assert len(d["adds"]) == 1
        assert len(d["rems"]) == 0
        assert d["adds"][0]["prefix"] == "10.0.0.0/8"
    
    def test_bgp_route_remove(self):
        """Test BGP route withdrawal"""
        prev = [BGPEntry(
            device="d", vrf="v", afi=AFI4, prefix="10.0.0.0/8", best=True,
            nh="1.1.1.1", as_path="65001", local_pref=100, med=50,
            origin="i", communities=[], communities_hash="", weight=None, peer="1.1.1.1"
        )]
        curr = []
        d = bgp_diff(prev, curr)
        assert len(d["adds"]) == 0
        assert len(d["rems"]) == 1
        assert d["rems"][0]["prefix"] == "10.0.0.0/8"