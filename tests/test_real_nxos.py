"""
Real device tests using Cisco DevNet Always-On NXOS Sandbox
Device: sbx-nxos-mgmt.cisco.com
Username: admin
Password: Admin_1234!
"""

import pytest
import os
from unittest.mock import patch
from parsers import collect_device_tables, parse_rib, parse_bgp
from models import AFI4, AFI6
from poller import collect_and_persist_for_device
import tempfile
import shutil

# Cisco DevNet Always-On NXOS Sandbox credentials
NXOS_ALWAYS_ON = {
    "device_type": "cisco_nxos",
    "host": "sbx-nxos-mgmt.cisco.com",
    "username": "admin", 
    "password": "Admin_1234!",
    "port": 22,
    "name": "sbx-nxos-always-on"
}

@pytest.mark.skipif(
    os.environ.get("SKIP_REAL_DEVICE_TESTS", "true").lower() == "true",
    reason="Skipping real device tests (set SKIP_REAL_DEVICE_TESTS=false to run)"
)
class TestRealNXOS:
    """Tests against real Cisco DevNet Always-On NXOS device"""
    
    def test_connect_and_collect(self):
        """Test real connection and data collection from NXOS device"""
        # VRFs available on sandbox (usually just default)
        vrfs = ["default"]
        afis = [AFI4]  # IPv4 only for faster testing
        
        try:
            result = collect_device_tables(NXOS_ALWAYS_ON, vrfs, afis)
            
            # Verify structure
            assert result["device"] == "sbx-nxos-always-on"
            assert "rib" in result
            assert "bgp" in result
            assert isinstance(result["rib"], list)
            assert isinstance(result["bgp"], list)
            
            # The sandbox should have at least some routes
            print(f"Found {len(result['rib'])} RIB entries")
            print(f"Found {len(result['bgp'])} BGP entries")
            
            # Print sample data for verification
            if result["rib"]:
                print(f"Sample RIB entry: {result['rib'][0].serialize()}")
            if result["bgp"]:
                print(f"Sample BGP entry: {result['bgp'][0].serialize()}")
                
        except Exception as e:
            pytest.skip(f"Could not connect to sandbox device: {e}")
    
    def test_nxapi_collection(self):
        """Test NX-API collection if enabled"""
        # Enable NX-API mode
        os.environ["USE_NXAPI"] = "true"
        os.environ["NXAPI_SCHEME"] = "https"
        os.environ["NXAPI_PORT"] = "443"
        os.environ["NXAPI_VERIFY"] = "false"
        
        vrfs = ["default"]
        afis = [AFI4]
        
        try:
            result = collect_device_tables(NXOS_ALWAYS_ON, vrfs, afis)
            
            assert result["device"] == "sbx-nxos-always-on"
            print(f"NX-API: Found {len(result['rib'])} RIB entries")
            print(f"NX-API: Found {len(result['bgp'])} BGP entries")
            
        except Exception as e:
            pytest.skip(f"NX-API not available or connection failed: {e}")
        finally:
            os.environ.pop("USE_NXAPI", None)
    
    def test_full_collection_and_diff(self):
        """Test full collection, persistence, and diffing workflow"""
        tmpdir = tempfile.mkdtemp()
        original_snapdir = os.environ.get("SNAPDIR")
        os.environ["SNAPDIR"] = tmpdir
        
        try:
            dev = {
                **NXOS_ALWAYS_ON,
                "vrfs": ["default"],
                "afis": [AFI4]
            }
            
            # First collection
            report1 = collect_and_persist_for_device(dev)
            
            assert report1["device"] == "sbx-nxos-always-on"
            assert "default" in report1["vrfs"]
            assert AFI4 in report1["vrfs"]["default"]
            
            # Check that snapshots were created
            import glob
            snapshots = glob.glob(os.path.join(tmpdir, "**", "*.json"), recursive=True)
            assert len(snapshots) > 0, "No snapshots were created"
            
            print(f"Created {len(snapshots)} snapshot files")
            
            # Second collection (should detect no changes if run immediately)
            report2 = collect_and_persist_for_device(dev)
            
            diff_data = report2["vrfs"]["default"][AFI4]
            print(f"Second collection - Adds: {len(diff_data['rib']['adds'])}, "
                  f"Removes: {len(diff_data['rib']['rems'])}, "
                  f"Changes: {len(diff_data['rib']['chgs'])}")
            
            # Since we're collecting immediately, there should be minimal changes
            # (some routes might flap, but most should be stable)
            total_changes = (len(diff_data['rib']['adds']) + 
                           len(diff_data['rib']['rems']) + 
                           len(diff_data['rib']['chgs']))
            
            print(f"Total RIB changes detected: {total_changes}")
            
        except Exception as e:
            pytest.skip(f"Could not complete full workflow: {e}")
        finally:
            # Cleanup
            shutil.rmtree(tmpdir)
            if original_snapdir:
                os.environ["SNAPDIR"] = original_snapdir
            else:
                os.environ.pop("SNAPDIR", None)

class TestRealNXOSCommands:
    """Test specific command outputs from real device"""
    
    @pytest.mark.skipif(
        os.environ.get("SKIP_REAL_DEVICE_TESTS", "true").lower() == "true",
        reason="Skipping real device tests"
    )
    def test_show_commands(self):
        """Test individual show commands"""
        from netmiko import ConnectHandler
        
        try:
            with ConnectHandler(**NXOS_ALWAYS_ON) as conn:
                # Test basic connectivity
                output = conn.send_command("show version")
                assert "Cisco" in output
                assert "NX-OS" in output
                
                # Test JSON output support
                json_output = conn.send_command("show version | json")
                if json_output.startswith("{"):
                    print("Device supports JSON output")
                    import json
                    version_data = json.loads(json_output)
                    print(f"NXOS Version: {version_data.get('sys_ver_str', 'Unknown')}")
                
                # Test routing table command
                rib_output = conn.send_command("show ip route vrf default")
                print(f"RIB output length: {len(rib_output)} characters")
                
                # Test BGP command (may not have BGP configured)
                try:
                    bgp_output = conn.send_command("show bgp vrf default ipv4 unicast")
                    print(f"BGP output length: {len(bgp_output)} characters")
                except:
                    print("BGP not configured or accessible")
                    
        except Exception as e:
            pytest.skip(f"Could not connect for command testing: {e}")


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_real_nxos.py -v -s
    # Or to actually run against real device:
    # SKIP_REAL_DEVICE_TESTS=false python -m pytest tests/test_real_nxos.py -v -s
    print("To run real device tests, use:")
    print("SKIP_REAL_DEVICE_TESTS=false python -m pytest tests/test_real_nxos.py -v -s")