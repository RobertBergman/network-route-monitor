"""
Test suite for storage.py - Snapshot persistence and loading
"""

import pytest
import os
import tempfile
import shutil
import gzip
import ujson as json
from freezegun import freeze_time
from storage import (
    ensure_dir, device_root, table_dir, diffs_dir,
    latest_path, ts_gz_path, write_latest, write_gz, read_latest
)

class TestStoragePaths:
    def test_device_root(self):
        assert device_root("/snap", "router1") == "/snap/router1"
    
    def test_table_dir(self):
        assert table_dir("/snap", "router1", "rib") == "/snap/router1/rib"
        assert table_dir("/snap", "router1", "bgp") == "/snap/router1/bgp"
    
    def test_diffs_dir(self):
        assert diffs_dir("/snap", "router1") == "/snap/router1/diffs"
    
    def test_latest_path(self):
        path = latest_path("/snap", "router1", "rib", "default", "ipv4")
        assert path == "/snap/router1/rib/default.ipv4.latest.json"
    
    @freeze_time("2024-01-15 10:30:45", tz_offset=0)
    def test_ts_gz_path(self):
        path = ts_gz_path("/snap", "router1", "rib", "default", "ipv4")
        assert path == "/snap/router1/rib/default.ipv4.20240115103045.json.gz"

class TestStorageOperations:
    def setup_method(self):
        """Create a temporary directory for testing"""
        self.tmpdir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.tmpdir)
    
    def test_ensure_dir(self):
        test_dir = os.path.join(self.tmpdir, "test", "nested", "dir")
        ensure_dir(test_dir)
        assert os.path.exists(test_dir)
        assert os.path.isdir(test_dir)
        
        # Should not fail if directory already exists
        ensure_dir(test_dir)
        assert os.path.exists(test_dir)
    
    def test_write_and_read_latest(self):
        test_path = os.path.join(self.tmpdir, "test.json")
        test_data = {
            "device": "router1",
            "routes": [
                {"prefix": "10.0.0.0/8", "protocol": "bgp"}
            ]
        }
        
        write_latest(test_path, test_data)
        assert os.path.exists(test_path)
        
        read_data = read_latest(test_path)
        assert read_data == test_data
    
    def test_write_latest_creates_parent_dirs(self):
        test_path = os.path.join(self.tmpdir, "deep", "nested", "test.json")
        test_data = {"test": "data"}
        
        write_latest(test_path, test_data)
        assert os.path.exists(test_path)
        
        read_data = read_latest(test_path)
        assert read_data == test_data
    
    def test_write_latest_atomic_replace(self):
        """Test that write_latest uses atomic replacement"""
        test_path = os.path.join(self.tmpdir, "test.json")
        
        # Write initial data
        initial_data = {"version": 1}
        write_latest(test_path, initial_data)
        
        # Write updated data
        updated_data = {"version": 2}
        write_latest(test_path, updated_data)
        
        # Should have the updated data
        read_data = read_latest(test_path)
        assert read_data == updated_data
        
        # Temp file should not exist
        assert not os.path.exists(test_path + ".tmp")
    
    def test_write_gz(self):
        test_path = os.path.join(self.tmpdir, "test.json.gz")
        test_data = {
            "device": "router1",
            "routes": [
                {"prefix": "10.0.0.0/8", "protocol": "bgp"},
                {"prefix": "192.168.0.0/16", "protocol": "ospf"}
            ]
        }
        
        write_gz(test_path, test_data)
        assert os.path.exists(test_path)
        
        # Read and verify gzipped data
        with gzip.open(test_path, "rt") as f:
            read_data = json.load(f)
        assert read_data == test_data
    
    def test_write_gz_creates_parent_dirs(self):
        test_path = os.path.join(self.tmpdir, "deep", "nested", "test.json.gz")
        test_data = {"test": "data"}
        
        write_gz(test_path, test_data)
        assert os.path.exists(test_path)
    
    def test_read_latest_nonexistent(self):
        """Test reading a non-existent file returns None"""
        test_path = os.path.join(self.tmpdir, "nonexistent.json")
        assert read_latest(test_path) is None
    
    def test_json_formatting(self):
        """Test that JSON files are formatted consistently"""
        test_path = os.path.join(self.tmpdir, "test.json")
        test_data = {
            "b": 2,
            "a": 1,
            "nested": {
                "z": 26,
                "y": 25
            }
        }
        
        write_latest(test_path, test_data)
        
        # Read file content directly
        with open(test_path, "r") as f:
            content = f.read()
        
        # Should be indented (pretty-printed)
        assert "  " in content  # Has indentation
        
        # Keys should be sorted
        assert content.index('"a"') < content.index('"b"')
    
    def test_large_data_handling(self):
        """Test handling of large datasets"""
        test_path = os.path.join(self.tmpdir, "large.json")
        
        # Create a large dataset
        large_data = {
            "routes": [
                {
                    "prefix": f"10.{i//256}.{i%256}.0/24",
                    "protocol": "bgp",
                    "as_path": "65001 65002 65003",
                    "communities": [f"65001:{j}" for j in range(10)]
                }
                for i in range(1000)
            ]
        }
        
        write_latest(test_path, large_data)
        read_data = read_latest(test_path)
        assert len(read_data["routes"]) == 1000
        
        # Test gzipped version
        gz_path = os.path.join(self.tmpdir, "large.json.gz")
        write_gz(gz_path, large_data)
        
        # Gzipped should be smaller than uncompressed
        uncompressed_size = os.path.getsize(test_path)
        compressed_size = os.path.getsize(gz_path)
        assert compressed_size < uncompressed_size