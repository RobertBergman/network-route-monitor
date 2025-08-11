"""
Test suite for parsers.py - RIB and BGP parsing with multiple vendor formats
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from parsers import (
    _try_json, _nxapi_request, _parse_with_genie,
    fetch_parsed, parse_rib, parse_bgp, collect_device_tables
)
from models import AFI4, AFI6

class TestJSONParsing:
    def test_try_json_success(self):
        """Test successful JSON parsing"""
        mock_conn = Mock()
        mock_conn.send_command.return_value = '{"test": "data"}'
        
        result = _try_json(mock_conn, "show version")
        assert result == {"test": "data"}
        mock_conn.send_command.assert_called_with("show version | json")
    
    def test_try_json_invalid(self):
        """Test handling of non-JSON response"""
        mock_conn = Mock()
        mock_conn.send_command.return_value = "Not JSON output"
        
        result = _try_json(mock_conn, "show version")
        assert result is None
    
    def test_try_json_exception(self):
        """Test exception handling"""
        mock_conn = Mock()
        mock_conn.send_command.side_effect = Exception("Command failed")
        
        result = _try_json(mock_conn, "show version")
        assert result is None

class TestNXAPIRequest:
    @patch('parsers.requests.post')
    @patch.dict('os.environ', {'NXAPI_SCHEME': 'https', 'NXAPI_PORT': '443', 'NXAPI_VERIFY': 'false'})
    def test_nxapi_success(self, mock_post):
        """Test successful NX-API request"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ins_api": {
                "outputs": {
                    "output": [
                        {"body": {"TABLE_vrf": {"ROW_vrf": []}}}
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = _nxapi_request("10.0.0.1", "admin", "password", ["show ip route"])
        assert result == {"TABLE_vrf": {"ROW_vrf": []}}
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://10.0.0.1:443/ins"
        assert call_args[1]["auth"] == ("admin", "password")
        assert call_args[1]["verify"] is False
    
    @patch('parsers.requests.post')
    def test_nxapi_failure(self, mock_post):
        """Test NX-API request failure"""
        mock_post.side_effect = Exception("Connection failed")
        
        result = _nxapi_request("10.0.0.1", "admin", "password", ["show ip route"])
        assert result is None

class TestRIBParsing:
    def test_parse_rib_genie_format(self):
        """Test parsing Genie-style RIB output"""
        parsed = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4": {
                            "routes": {
                                "10.0.0.0/24": {
                                    "route_preference": {
                                        "protocol": "ospf",
                                        "preference": 110
                                    },
                                    "metric": 20,
                                    "active": True,
                                    "next_hop": {
                                        "next_hop_list": {
                                            "1": {
                                                "next_hop": "192.168.1.1",
                                                "outgoing_interface": "Eth1/1"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        entries = parse_rib("router1", "iosxe", "default", AFI4, parsed)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.prefix == "10.0.0.0/24"
        assert entry.protocol == "ospf"
        assert entry.distance == 110
        assert entry.metric == 20
        assert entry.best is True
        assert len(entry.nexthops) == 1
        nh = list(entry.nexthops)[0]
        assert nh.nh == "192.168.1.1"
        assert nh.iface == "Eth1/1"
    
    def test_parse_rib_nxapi_format(self):
        """Test parsing NX-API style RIB output"""
        parsed = {
            "TABLE_vrf": {
                "ROW_vrf": {
                    "vrf-name-out": "default",
                    "TABLE_addrf": {
                        "ROW_addrf": [{
                            "addrf": "ipv4",
                            "TABLE_prefix": {
                                "ROW_prefix": {
                                    "ipprefix": "10.0.0.0/24",
                                    "ubest-source": "ospf-1",
                                    "ubest-distance": 110,
                                    "ubest-metric": 20,
                                    "ubest": "true",
                                    "TABLE_paths": {
                                        "ROW_paths": {
                                            "ipprefix": "192.168.1.1",
                                            "ifname": "Ethernet1/1"
                                        }
                                    }
                                }
                            }
                        }]
                    }
                }
            }
        }
        
        entries = parse_rib("nx-switch1", "nxos", "default", AFI4, parsed)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.prefix == "10.0.0.0/24"
        assert entry.protocol == "ospf-1"
        assert entry.distance == 110
        assert entry.metric == 20
        assert entry.best is True
    
    def test_parse_rib_ecmp(self):
        """Test parsing ECMP routes with multiple nexthops"""
        parsed = {
            "vrf": {
                "default": {
                    "address_family": {
                        "ipv4": {
                            "routes": {
                                "10.0.0.0/24": {
                                    "route_preference": {
                                        "protocol": "ospf",
                                        "preference": 110
                                    },
                                    "metric": 20,
                                    "active": True,
                                    "next_hop": {
                                        "next_hop_list": {
                                            "1": {
                                                "next_hop": "192.168.1.1",
                                                "outgoing_interface": "Eth1/1"
                                            },
                                            "2": {
                                                "next_hop": "192.168.1.2",
                                                "outgoing_interface": "Eth1/2"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        entries = parse_rib("router1", "iosxe", "default", AFI4, parsed)
        assert len(entries) == 1
        entry = entries[0]
        assert len(entry.nexthops) == 2
        nh_ips = {nh.nh for nh in entry.nexthops}
        assert "192.168.1.1" in nh_ips
        assert "192.168.1.2" in nh_ips

class TestBGPParsing:
    def test_parse_bgp_genie_format(self):
        """Test parsing Genie-style BGP output"""
        parsed = {
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
                                            "as_path": ["65001", "65002"],
                                            "localpref": 100,
                                            "med": 50,
                                            "origin_code": "i",
                                            "community": "65001:100 65002:200",
                                            "weight": 32768,
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
        
        entries = parse_bgp("router1", "iosxe", "default", AFI4, parsed)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.prefix == "10.0.0.0/8"
        assert entry.best is True
        assert entry.nh == "192.168.1.1"
        assert entry.as_path == "65001 65002"
        assert entry.local_pref == 100
        assert entry.med == 50
        assert entry.origin == "i"
        assert "65001:100" in entry.communities
        assert "65002:200" in entry.communities
    
    def test_parse_bgp_nxapi_format(self):
        """Test parsing NX-API style BGP output"""
        parsed = {
            "TABLE_vrf": {
                "ROW_vrf": {
                    "vrf-name-out": "default",
                    "TABLE_af": {
                        "ROW_af": {
                            "af": "ipv4 unicast",
                            "TABLE_prefix": {
                                "ROW_prefix": {
                                    "prefix": "10.0.0.0/8",
                                    "TABLE_path": {
                                        "ROW_path": {
                                            "best": "true",
                                            "nexthop": "192.168.1.1",
                                            "aspath": "65001 65002",
                                            "localpref": 100,
                                            "metric": 50,
                                            "origin": "i",
                                            "community": ["65001:100", "65002:200"],
                                            "weight": 32768,
                                            "neighbor_id": "192.168.1.2"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        entries = parse_bgp("nx-switch1", "nxos", "default", AFI4, parsed)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.prefix == "10.0.0.0/8"
        assert entry.best is True
        assert entry.nh == "192.168.1.1"
        assert entry.as_path == "65001 65002"
    
    def test_parse_bgp_multiple_paths(self):
        """Test parsing multiple BGP paths for same prefix"""
        parsed = {
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
                                            "neighbor": "192.168.1.1"
                                        },
                                        "2": {
                                            "bestpath": False,
                                            "next_hop": "192.168.1.2",
                                            "as_path": ["65002"],
                                            "localpref": 90,
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
        
        entries = parse_bgp("router1", "iosxe", "default", AFI4, parsed)
        assert len(entries) == 2
        best_entries = [e for e in entries if e.best]
        assert len(best_entries) == 1
        assert best_entries[0].local_pref == 100

class TestDeviceCollection:
    @patch('parsers.ConnectHandler')
    def test_collect_device_tables(self, mock_connect_handler):
        """Test full device collection flow"""
        mock_conn = MagicMock()
        mock_connect_handler.return_value = mock_conn
        
        # Mock successful JSON responses
        mock_conn.send_command.side_effect = [
            '{"vrf": {"default": {"address_family": {"ipv4": {"routes": {}}}}}}',  # RIB IPv4
            '{"vrf": {"default": {"address_family": {"ipv4 unicast": {"routes": {}}}}}}',  # BGP IPv4
            '{"vrf": {"default": {"address_family": {"ipv6": {"routes": {}}}}}}',  # RIB IPv6
            '{"vrf": {"default": {"address_family": {"ipv6 unicast": {"routes": {}}}}}}'  # BGP IPv6
        ]
        
        dev = {
            "name": "router1",
            "device_type": "cisco_xe",
            "host": "10.0.0.1",
            "username": "admin",
            "password": "password"
        }
        
        result = collect_device_tables(dev, ["default"], [AFI4, AFI6])
        
        assert result["device"] == "router1"
        assert "rib" in result
        assert "bgp" in result
        assert isinstance(result["rib"], list)
        assert isinstance(result["bgp"], list)
        
        # Verify connection was properly closed
        mock_conn.disconnect.assert_called_once()
    
    @patch('parsers.ConnectHandler')
    def test_collect_device_error_handling(self, mock_connect_handler):
        """Test error handling during collection"""
        mock_conn = MagicMock()
        mock_connect_handler.return_value = mock_conn
        
        # Mock command failure
        mock_conn.send_command.side_effect = Exception("Command failed")
        
        dev = {
            "name": "router1",
            "device_type": "cisco_xe",
            "host": "10.0.0.1",
            "username": "admin",
            "password": "password"
        }
        
        result = collect_device_tables(dev, ["default"], [AFI4])
        
        # Should still return structure even if commands fail
        assert result["device"] == "router1"
        assert result["rib"] == []
        assert result["bgp"] == []
        
        # Connection should still be closed
        mock_conn.disconnect.assert_called_once()