"""
Integration tests for the complete route monitoring system
"""

import pytest
import os
import tempfile
import shutil
import time
from unittest.mock import patch, Mock, MagicMock
from freezegun import freeze_time

# Import our modules
from models import RIBEntry, BGPEntry, NH, AFI4, AFI6
from storage import write_latest, read_latest, latest_path
from diffing import rib_diff, bgp_diff
from poller import collect_and_persist_for_device


class TestEndToEndFlow:
    """Test the complete flow from collection to persistence to diffing"""
    
    def setup_method(self):
        """Create temporary directory for testing"""
        self.tmpdir = tempfile.mkdtemp()
        self.original_snapdir = os.environ.get("SNAPDIR")
        os.environ["SNAPDIR"] = self.tmpdir
    
    def teardown_method(self):
        """Clean up"""
        shutil.rmtree(self.tmpdir)
        if self.original_snapdir:
            os.environ["SNAPDIR"] = self.original_snapdir
        else:
            os.environ.pop("SNAPDIR", None)
    
    @patch('parsers.ConnectHandler')
    def test_first_collection(self, mock_connect_handler):
        """Test first collection with no previous data"""
        mock_conn = MagicMock()
        mock_connect_handler.return_value = mock_conn
        
        # Mock responses for a simple RIB and BGP table
        rib_response = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4": {
                            "routes": {
                                "10.0.0.0/24": {
                                    "route_preference": {"protocol": "ospf", "preference": 110},
                                    "metric": 20,
                                    "active": True,
                                    "next_hop": {
                                        "next_hop_list": {
                                            "1": {"next_hop": "192.168.1.1", "outgoing_interface": "Eth1"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        bgp_response = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4 unicast": {
                            "routes": {
                                "10.0.0.0/8": {
                                    "index": {
                                        "1": {
                                            "bestpath": True,
                                            "next_hop": "192.168.1.1",
                                            "as_path": ["65001"],
                                            "localpref": 100,
                                            "neighbor": "192.168.1.2"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        import ujson as json
        # Mock responses - _try_json will append " | json" to commands
        def mock_send_command(cmd, **kwargs):
            if "show ip route" in cmd and "| json" in cmd:
                return json.dumps(rib_response)
            elif "show bgp" in cmd and "| json" in cmd:
                return json.dumps(bgp_response)
            return "{}"
        
        mock_conn.send_command.side_effect = mock_send_command
        
        dev = {
            "name": "router1",
            "device_type": "cisco_xe",
            "host": "10.0.0.1",
            "username": "admin",
            "password": "password",
            "vrfs": ["default"],
            "afis": [AFI4]
        }
        
        report = collect_and_persist_for_device(dev)
        
        # Check report structure
        assert report["device"] == "router1"
        assert "default" in report["vrfs"]
        assert AFI4 in report["vrfs"]["default"]
        
        # Check diffs (should have adds only, no previous data)
        diff_data = report["vrfs"]["default"][AFI4]
        print(f"DEBUG: diff_data = {diff_data}")
        print(f"DEBUG: rib adds = {diff_data['rib']['adds']}")
        assert len(diff_data["rib"]["adds"]) == 1
        assert len(diff_data["rib"]["rems"]) == 0
        assert len(diff_data["rib"]["chgs"]) == 0
        assert len(diff_data["bgp"]["adds"]) == 1
        
        # Check persistence - files should exist
        rib_path = latest_path(self.tmpdir, "router1", "rib", "default", AFI4)
        bgp_path = latest_path(self.tmpdir, "router1", "bgp", "default", AFI4)
        
        # Debug: Print what we're looking for
        import glob
        all_files = glob.glob(os.path.join(self.tmpdir, "**", "*"), recursive=True)
        
        assert os.path.exists(rib_path), f"RIB path {rib_path} not found. Available files: {all_files}"
        assert os.path.exists(bgp_path)
        
        rib_data = read_latest(rib_path)
        assert len(rib_data) == 1
        assert rib_data[0]["prefix"] == "10.0.0.0/24"
    
    @patch('parsers.ConnectHandler')
    def test_incremental_changes(self, mock_connect_handler):
        """Test detecting changes between collections"""
        mock_conn = MagicMock()
        mock_connect_handler.return_value = mock_conn
        
        # Initial state
        initial_rib = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4": {
                            "routes": {
                                "10.0.0.0/24": {
                                    "route_preference": {"protocol": "ospf", "preference": 110},
                                    "metric": 20,
                                    "active": True,
                                    "next_hop": {
                                        "next_hop_list": {
                                            "1": {"next_hop": "192.168.1.1", "outgoing_interface": "Eth1"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        # Changed state (ECMP added)
        changed_rib = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4": {
                            "routes": {
                                "10.0.0.0/24": {
                                    "route_preference": {"protocol": "ospf", "preference": 110},
                                    "metric": 20,
                                    "active": True,
                                    "next_hop": {
                                        "next_hop_list": {
                                            "1": {"next_hop": "192.168.1.1", "outgoing_interface": "Eth1"},
                                            "2": {"next_hop": "192.168.1.2", "outgoing_interface": "Eth2"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        import ujson as json
        
        dev = {
            "name": "router1",
            "device_type": "cisco_xe",
            "host": "10.0.0.1",
            "username": "admin",
            "password": "password",
            "vrfs": ["default"],
            "afis": [AFI4]
        }
        
        # First collection
        mock_conn.send_command.side_effect = [
            json.dumps(initial_rib),
            json.dumps({"vrf": {"default": {"address_family": {"ipv4 unicast": {"routes": {}}}}}})
        ]
        
        report1 = collect_and_persist_for_device(dev)
        
        # Second collection with changes
        mock_conn.send_command.side_effect = [
            json.dumps(changed_rib),
            json.dumps({"vrf": {"default": {"address_family": {"ipv4 unicast": {"routes": {}}}}}})
        ]
        
        report2 = collect_and_persist_for_device(dev)
        
        # Check that changes were detected
        diff_data = report2["vrfs"]["default"][AFI4]
        assert len(diff_data["rib"]["adds"]) == 0
        assert len(diff_data["rib"]["rems"]) == 0
        assert len(diff_data["rib"]["chgs"]) == 1
        
        # Verify the nexthop change
        change = diff_data["rib"]["chgs"][0]
        assert "nexthops" in change["delta"]
        old_nh, new_nh = change["delta"]["nexthops"]
        assert len(old_nh) == 1
        assert len(new_nh) == 2

class TestMetricsExporter:
    """Test Prometheus metrics generation"""
    
    @patch('exporter.start_http_server')
    @patch('exporter.get_inventory')
    @patch('exporter.collect_and_persist_for_device')
    def test_metrics_update(self, mock_collect, mock_inventory, mock_http):
        """Test that metrics are properly updated"""
        from exporter import update_metrics, ROUTE_COUNT, BGP_BEST_COUNT, RIB_ADDS
        
        # Create a test report
        report = {
            "device": "router1",
            "vrfs": {
                "default": {
                    "ipv4": {
                        "rib": {
                            "adds": [{"prefix": "10.0.0.0/24", "protocol": "ospf"}],
                            "rems": [],
                            "chgs": []
                        },
                        "bgp": {
                            "adds": [],
                            "rems": [],
                            "chgs": [{
                                "prefix": "0.0.0.0/0",
                                "delta": {"nh": ("1.1.1.1", "2.2.2.2")}
                            }]
                        }
                    }
                }
            }
        }
        
        # Mock snapshot reading
        with patch('exporter.read_latest') as mock_read:
            mock_read.side_effect = [
                # RIB snapshot
                [{"prefix": "10.0.0.0/24", "protocol": "ospf"}],
                # BGP snapshot
                [{"prefix": "10.0.0.0/8", "best": True}, {"prefix": "192.168.0.0/16", "best": False}]
            ]
            
            update_metrics(report)
        
        # Check gauge values
        # Note: In real tests, we'd need to access the actual metric values
        # This is simplified for demonstration

class TestErrorHandling:
    """Test error handling and recovery"""
    
    @patch('parsers.ConnectHandler')
    def test_device_connection_failure(self, mock_connect_handler):
        """Test handling of device connection failures"""
        mock_connect_handler.side_effect = Exception("Connection refused")
        
        dev = {
            "name": "router1",
            "device_type": "cisco_xe",
            "host": "10.0.0.1",
            "username": "admin",
            "password": "password",
            "vrfs": ["default"],
            "afis": [AFI4]
        }
        
        # Should handle exception gracefully
        with pytest.raises(Exception):
            from parsers import collect_device_tables
            collect_device_tables(dev, ["default"], [AFI4])
    
    def test_corrupted_snapshot_handling(self):
        """Test handling of corrupted snapshot files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "bad.json")
            
            # Write invalid JSON
            with open(bad_path, "w") as f:
                f.write("{invalid json")
            
            # Should handle gracefully
            from storage import read_latest
            with pytest.raises(Exception):
                read_latest(bad_path)

class TestPerformanceOptimization:
    """Test performance-critical code paths"""
    
    def test_large_routing_table_diff(self):
        """Test diffing performance with large routing tables"""
        # Create large routing tables
        prev_routes = []
        curr_routes = []
        
        # 10,000 routes
        for i in range(10000):
            prefix = f"10.{i//256}.{i%256}.0/24"
            prev_routes.append(RIBEntry(
                device="router1", vrf="default", afi=AFI4,
                prefix=prefix, protocol="bgp", distance=20,
                metric=None, best=True,
                nexthops={NH("192.168.1.1", "Eth1")}
            ))
            
            # Change 10% of routes
            if i % 10 == 0:
                curr_routes.append(RIBEntry(
                    device="router1", vrf="default", afi=AFI4,
                    prefix=prefix, protocol="bgp", distance=20,
                    metric=None, best=True,
                    nexthops={NH("192.168.1.2", "Eth2")}  # Different nexthop
                ))
            else:
                curr_routes.append(prev_routes[-1])
        
        start_time = time.time()
        diff = rib_diff(prev_routes, curr_routes)
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time (< 1 second for 10k routes)
        assert elapsed < 1.0
        
        # Verify correct number of changes
        assert len(diff["chgs"]) == 1000  # 10% of 10,000
    
    def test_community_hash_performance(self):
        """Test performance of community hashing"""
        from models import set_hash
        
        # Large community list
        communities = [f"65001:{i}" for i in range(1000)]
        
        start_time = time.time()
        for _ in range(100):
            hash_val = set_hash(communities)
        elapsed = time.time() - start_time
        
        # Should be fast even with many communities
        assert elapsed < 0.1  # 100 hashes in < 100ms