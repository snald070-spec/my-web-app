#!/usr/bin/env python3
"""
Migrate existing emp_ids to name-based IDs.
This script regenerates all emp_ids from user names, handling duplicates with B/C/D... suffixes.
All related records are updated to maintain referential integrity.
"""

import sys
import re
from sqlalchemy.exc import SQLAlchemyError
from database import SessionLocal
import models


def generate_emp_id_from_name(name: str, db, existing_ids: set) -> str:
    """
    Generate emp_id from user's name.
    If duplicate exists, append B, C, D, etc.
    """
    base_name = re.sub(r"\s+", "", (name or "").lower().strip())
    if not base_name:
        raise ValueError(f"Cannot generate ID from empty name: '{name}'")
    
    # Check if base name is available
    if base_name not in existing_ids:
        return base_name
    
    # Try appending B, C, D, ... Z
    for suffix_ord in range(ord('B'), ord('Z') + 1):
        suffix_char = chr(suffix_ord)
        emp_id = base_name + suffix_char.lower()
        if emp_id not in existing_ids:
            return emp_id
    
    # Fallback: if all single suffixes used, try double (bb, bc, ...)
    for suffix_ord1 in range(ord('B'), ord('Z') + 1):
        for suffix_ord2 in range(ord('B'), ord('Z') + 1):
            suffix = chr(suffix_ord1).lower() + chr(suffix_ord2).lower()
            emp_id = base_name + suffix
            if emp_id not in existing_ids:
                return emp_id
    
    raise ValueError(f"Cannot generate unique ID for name '{name}'. Too many duplicates.")


def rekey_user_references(db, old_emp_id: str, new_emp_id: str):
    """Update all records that reference this emp_id."""
    if old_emp_id == new_emp_id:
        return

    tables_and_columns = [
        (models.UserAuditLog, "target_emp_id"),
        (models.UserAuditLog, "actor_emp_id"),
        (models.Notice, "created_by"),
        (models.Notice, "updated_by"),
        (models.MemberProfile, "emp_id"),
        (models.MemberProfile, "updated_by"),
        (models.AttendanceEvent, "created_by"),
        (models.AttendanceVote, "emp_id"),
        (models.LeagueTeamAssignment, "emp_id"),
        (models.LeagueTeamAssignment, "updated_by"),
        (models.AttendanceEventSetting, "updated_by"),
        (models.AttendanceReminderLog, "emp_id"),
        (models.AttendanceReminderLog, "sent_by"),
    ]
    
    # Handle MembershipPayment separately if it exists in models
    if hasattr(models, 'MembershipPayment'):
        tables_and_columns.extend([
            (models.MembershipPayment, "emp_id"),
            (models.MembershipPayment, "marked_by"),
        ])
    
    if hasattr(models, 'FeeReminderLog'):
        tables_and_columns.append((models.FeeReminderLog, "sent_by"))
    
    for model_class, column_name in tables_and_columns:
        try:
            column = getattr(model_class, column_name)
            db.query(model_class).filter(column == old_emp_id).update(
                {column: new_emp_id}, synchronize_session=False
            )
        except Exception as e:
            print(f"Warning: Could not update {model_class.__tablename__}.{column_name}: {e}")


def run_migration():
    """Main migration logic."""
    db = SessionLocal()
    try:
        print("=== Starting emp_id migration ===\n")
        
        # Get all users sorted by creation date (stable ordering)
        users = db.query(models.User).order_by(models.User.created_at).all()
        
        if not users:
            print("No users found. Migration skipped.")
            return 0
        
        print(f"Found {len(users)} users to migrate.\n")
        
        migration_map = {}  # old_emp_id -> new_emp_id
        existing_ids = set()  # Track newly generated IDs to avoid duplicates during migration
        
        # First pass: generate all new emp_ids
        for user in users:
            try:
                new_emp_id = generate_emp_id_from_name(user.name, db, existing_ids)
                migration_map[user.emp_id] = new_emp_id
                existing_ids.add(new_emp_id)
                
                if user.emp_id != new_emp_id:
                    print(f"  {user.emp_id} -> {new_emp_id}  ({user.name})")
                else:
                    print(f"  {user.emp_id} (unchanged)  ({user.name})")
            except ValueError as e:
                print(f"ERROR: {e}")
                raise
        
        print(f"\nMigration map generated. Applying updates...\n")
        
        # Second pass: update all records
        updates = 0
        for old_emp_id, new_emp_id in migration_map.items():
            if old_emp_id != new_emp_id:
                rekey_user_references(db, old_emp_id, new_emp_id)
                
                # Update the user record itself
                user = db.query(models.User).filter(models.User.emp_id == old_emp_id).first()
                if user:
                    user.emp_id = new_emp_id
                    updates += 1
        
        # Commit all changes
        db.commit()
        print(f"Updated {updates} user records and all references.")
        print("\n=== Migration completed successfully ===")
        return 0
        
    except Exception as e:
        db.rollback()
        print(f"\nMigration FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(run_migration())
