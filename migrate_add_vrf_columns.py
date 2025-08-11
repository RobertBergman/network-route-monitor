#!/usr/bin/env python3
"""
Migration script to add VRF columns to the devices table.
Run this to update existing databases with the new schema.
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def get_db_url() -> str:
    """Get database URL from environment or use default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://routemonitor:routemonitor@localhost/routemonitor"
    )

def migrate():
    """Add VRF columns to devices table if they don't exist."""
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'devices' 
            AND column_name IN ('vrfs', 'vrfs_updated_at')
        """))
        
        existing_columns = [row[0] for row in result]
        
        # Add vrfs column if it doesn't exist
        if 'vrfs' not in existing_columns:
            print("Adding 'vrfs' column to devices table...")
            conn.execute(text("""
                ALTER TABLE devices 
                ADD COLUMN vrfs TEXT
            """))
            conn.commit()
            print("  ✓ Added 'vrfs' column")
        else:
            print("  'vrfs' column already exists")
        
        # Add vrfs_updated_at column if it doesn't exist
        if 'vrfs_updated_at' not in existing_columns:
            print("Adding 'vrfs_updated_at' column to devices table...")
            conn.execute(text("""
                ALTER TABLE devices 
                ADD COLUMN vrfs_updated_at TIMESTAMP
            """))
            conn.commit()
            print("  ✓ Added 'vrfs_updated_at' column")
        else:
            print("  'vrfs_updated_at' column already exists")
        
        print("\nMigration completed successfully!")
        
        # Show current schema
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'devices'
            ORDER BY ordinal_position
        """))
        
        print("\nCurrent devices table schema:")
        for row in result:
            nullable = "NULL" if row[2] == 'YES' else "NOT NULL"
            print(f"  - {row[0]}: {row[1]} {nullable}")

if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)