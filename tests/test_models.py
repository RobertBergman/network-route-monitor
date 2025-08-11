"""
Test suite for models.py - data structures and normalization
"""

import pytest
from models import (
    NH, RIBEntry, BGPEntry, AFI4, AFI6,
    normalize_communities, set_hash
)

class TestNH:
    def test_nh_creation(self):
        nh = NH(nh="10.0.0.1", iface="eth0")
        assert nh.nh == "10.0.0.1"
        assert nh.iface == "eth0"
    
    def test_nh_frozen(self):
        nh = NH(nh="10.0.0.1", iface="eth0")
        with pytest.raises(AttributeError):
            nh.nh = "10.0.0.2"
    
    def test_nh_equality(self):
        nh1 = NH(nh="10.0.0.1", iface="eth0")
        nh2 = NH(nh="10.0.0.1", iface="eth0")
        nh3 = NH(nh="10.0.0.2", iface="eth0")
        assert nh1 == nh2
        assert nh1 != nh3

class TestCommunityNormalization:
    def test_empty_communities(self):
        assert normalize_communities(None) == []
        assert normalize_communities([]) == []
        assert normalize_communities("") == []
    
    def test_string_communities(self):
        assert normalize_communities("65001:100") == ["65001:100"]
        assert normalize_communities("65001:100 65002:200") == ["65001:100", "65002:200"]
    
    def test_list_communities(self):
        assert normalize_communities(["65001:100", "65002:200"]) == ["65001:100", "65002:200"]
    
    def test_mixed_communities(self):
        assert normalize_communities(["65001:100 65002:200", "65003:300"]) == [
            "65001:100", "65002:200", "65003:300"
        ]
    
    def test_duplicate_communities(self):
        assert normalize_communities("65001:100 65001:100 65002:200") == ["65001:100", "65002:200"]
    
    def test_sorted_communities(self):
        result = normalize_communities("65002:200 65001:100")
        assert result == ["65001:100", "65002:200"]

class TestSetHash:
    def test_empty_hash(self):
        h = set_hash([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex digest
    
    def test_consistent_hash(self):
        items = ["65001:100", "65002:200"]
        h1 = set_hash(items)
        h2 = set_hash(items)
        assert h1 == h2
    
    def test_order_matters(self):
        h1 = set_hash(["a", "b"])
        h2 = set_hash(["b", "a"])
        assert h1 != h2

class TestRIBEntry:
    def test_rib_entry_creation(self):
        nh_set = {NH("10.0.0.1", "eth0"), NH("10.0.0.2", "eth1")}
        entry = RIBEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="192.168.1.0/24",
            protocol="ospf",
            distance=110,
            metric=20,
            best=True,
            nexthops=nh_set
        )
        assert entry.device == "router1"
        assert entry.vrf == "default"
        assert entry.prefix == "192.168.1.0/24"
        assert len(entry.nexthops) == 2
    
    def test_rib_entry_key(self):
        entry = RIBEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="192.168.1.0/24",
            protocol="ospf",
            distance=110,
            metric=20,
            best=True
        )
        key = entry.key()
        assert key == ("default", AFI4, "192.168.1.0/24", "ospf")
    
    def test_rib_entry_serialize(self):
        nh_set = {NH("10.0.0.1", "eth0")}
        entry = RIBEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="192.168.1.0/24",
            protocol="ospf",
            distance=110,
            metric=20,
            best=True,
            nexthops=nh_set
        )
        data = entry.serialize()
        assert data["device"] == "router1"
        assert data["vrf"] == "default"
        assert data["afi"] == AFI4
        assert data["prefix"] == "192.168.1.0/24"
        assert data["protocol"] == "ospf"
        assert data["distance"] == 110
        assert data["metric"] == 20
        assert data["best"] is True
        assert len(data["nexthops"]) == 1
        assert data["nexthops"][0] == {"nh": "10.0.0.1", "iface": "eth0"}
    
    def test_rib_entry_ecmp_serialize(self):
        """Test that nexthops are sorted for consistent serialization"""
        nh_set = {NH("10.0.0.2", "eth1"), NH("10.0.0.1", "eth0")}
        entry = RIBEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="192.168.1.0/24",
            protocol="ospf",
            distance=110,
            metric=20,
            best=True,
            nexthops=nh_set
        )
        data = entry.serialize()
        # Should be sorted by (nh, iface)
        assert data["nexthops"][0]["nh"] == "10.0.0.1"
        assert data["nexthops"][1]["nh"] == "10.0.0.2"

class TestBGPEntry:
    def test_bgp_entry_creation(self):
        entry = BGPEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="10.0.0.0/8",
            best=True,
            nh="192.168.1.1",
            as_path="65001 65002",
            local_pref=100,
            med=50,
            origin="i",
            communities=["65001:100"],
            communities_hash="abcd1234",
            weight=32768,
            peer="192.168.1.2"
        )
        assert entry.device == "router1"
        assert entry.prefix == "10.0.0.0/8"
        assert entry.best is True
        assert entry.as_path == "65001 65002"
    
    def test_bgp_entry_key(self):
        entry = BGPEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="10.0.0.0/8",
            best=True,
            nh="192.168.1.1",
            as_path="65001",
            local_pref=100,
            med=None,
            origin="i",
            communities=[],
            communities_hash="",
            weight=None,
            peer="192.168.1.2"
        )
        key = entry.key()
        assert key == ("default", AFI4, "10.0.0.0/8")
    
    def test_bgp_entry_serialize(self):
        communities = ["65001:100", "65002:200"]
        entry = BGPEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="10.0.0.0/8",
            best=True,
            nh="192.168.1.1",
            as_path="65001 65002",
            local_pref=100,
            med=50,
            origin="i",
            communities=communities,
            communities_hash=set_hash(communities),
            weight=32768,
            peer="192.168.1.2",
            originator_id="10.0.0.1",
            cluster_list=["10.0.0.1", "10.0.0.2"]
        )
        data = entry.serialize()
        assert data["device"] == "router1"
        assert data["best"] is True
        assert data["as_path"] == "65001 65002"
        assert data["local_pref"] == 100
        assert data["med"] == 50
        assert data["originator_id"] == "10.0.0.1"
        assert data["cluster_list"] == ["10.0.0.1", "10.0.0.2"]
    
    def test_bgp_entry_community_truncation(self):
        """Test that communities are truncated to 64 entries in serialization"""
        communities = [f"65001:{i}" for i in range(100)]
        entry = BGPEntry(
            device="router1",
            vrf="default",
            afi=AFI4,
            prefix="10.0.0.0/8",
            best=True,
            nh="192.168.1.1",
            as_path="65001",
            local_pref=100,
            med=None,
            origin="i",
            communities=communities,
            communities_hash=set_hash(communities),
            weight=None,
            peer="192.168.1.2"
        )
        data = entry.serialize()
        assert len(data["communities"]) == 64
        assert data["communities_hash"] == set_hash(communities)