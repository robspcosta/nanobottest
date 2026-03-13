"""Database manager forNanobot."""

import os
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import Column, DateTime, String, Boolean, Integer, ForeignKey, create_engine, select, func, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # platform:external_id
    platform = Column(String, index=True)
    external_id = Column(String, index=True)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    contacts = relationship("Contact", back_populates="owner", cascade="all, delete-orphan")
    finance_records = relationship("FinanceRecord", back_populates="owner", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String, ForeignKey("users.id"), index=True)
    name = Column(String, index=True)
    platform = Column(String)
    external_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="contacts")


class Knowledge(Base):
    __tablename__ = "knowledge"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String, ForeignKey("users.id"), index=True)
    content = Column(String)
    metadata_json = Column(String) # For extra tags/source
    embedding = Column(Vector(1536)) # Default to 1536 for OpenAI/many models
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User")


class FinanceRecord(Base):
    __tablename__ = "finance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String, ForeignKey("users.id"), index=True)
    amount = Column(Integer) # In cents or using numeric
    category = Column(String, index=True)
    description = Column(String)
    type = Column(String) # 'income' or 'expense'
    date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="finance_records")


class DatabaseManager:
    """Manages database connection and operations."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist and ensure extension."""
        try:
            # First ensure pgvector extension
            try:
                with self.engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()
            except Exception as e:
                logger.warning("Could not ensure pgvector extension (might already exist or permission denied): {}", e)
            
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables verified/created.")
        except Exception as e:
            logger.error("Failed to create database tables: {}", e)

    def _normalize_id(self, platform: str, external_id: str) -> str:
        """Normalize IDs (especially phone numbers) for consistency."""
        import re
        if not external_id:
            return ""
        external_id = str(external_id).strip()
        
        if platform == "whatsapp":
            # 1. Remove all non-digits
            clean = re.sub(r"\D", "", external_id)
            
            # 2. Brazil Specific Normalization
            # Brazil numbers are 55 + DDD (2) + 8 or 9 digits.
            if clean.startswith("55") and (len(clean) == 12 or len(clean) == 13):
                ddd = clean[2:4]
                number = clean[4:]
                # If 9 digits mobile (9xxxxxxx), remove the 9th digit '9'
                # WhatsApp JIDs in Brazil often ignore the 9th digit.
                if len(number) == 9 and number.startswith("9"):
                    number = number[1:]
                return f"55{ddd}{number}"
            
            # If provided without 55 prefix (e.g. 5196057577 or 51996057577)
            if not clean.startswith("55") and (len(clean) == 10 or len(clean) == 11):
                return self._normalize_id(platform, f"55{clean}")
                
            return clean
        return external_id

    def is_allowed(self, platform: str, external_id: str) -> bool:
        """Check if a user is allowed access."""
        external_id = self._normalize_id(platform, external_id)
        with self.SessionLocal() as session:
            stmt = select(User).where(
                User.platform == platform,
                User.external_id == external_id,
                User.is_active == True
            )
            user = session.execute(stmt).scalar_one_or_none()
            return user is not None

    def add_user(self, platform: str, external_id: str, role: str = "user") -> bool:
        """Add a new user to the database."""
        external_id = self._normalize_id(platform, external_id)
        with self.SessionLocal() as session:
            # Check if exists
            stmt = select(User).where(User.platform == platform, User.external_id == external_id)
            if session.execute(stmt).scalar_one_or_none():
                return False

            user = User(
                id=f"{platform}:{external_id}",
                platform=platform,
                external_id=external_id,
                role=role,
                is_active=True
            )
            session.add(user)
            session.commit()
            logger.info("Added user {}:{} with role {}", platform, external_id, role)
            return True

    def remove_user(self, platform: str, external_id: str) -> bool:
        """Deactivate a user."""
        with self.SessionLocal() as session:
            stmt = select(User).where(User.platform == platform, User.external_id == str(external_id))
            user = session.execute(stmt).scalar_one_or_none()
            if user:
                user.is_active = False
                session.commit()
                return True
            return False

    def list_users(self) -> list[dict[str, Any]]:
        """List all users."""
        with self.SessionLocal() as session:
            stmt = select(User)
            users = session.execute(stmt).scalars().all()
            return [
                {
                    "platform": u.platform,
                    "external_id": u.external_id,
                    "role": u.role,
                    "is_active": u.is_active
                }
                for u in users
            ]

    def seed_users(self, config_users: dict[str, list[str]]) -> None:
        """Seed/Sync database from config. Ensures config users exist and are normalized."""
        logger.info("Syncing users from config...")
        with self.SessionLocal() as session:
            for platform, ids in config_users.items():
                for sid in ids:
                    if sid == "*": continue
                    
                    # Extract numeric ID and normalize
                    raw_id = sid.split("|")[0]
                    external_id = self._normalize_id(platform, raw_id)
                    user_db_id = f"{platform}:{external_id}"
                    
                    # Check for existing user
                    stmt = select(User).where(User.id == user_db_id)
                    user = session.execute(stmt).scalar_one_or_none()
                    
                    if not user:
                        user = User(
                            id=user_db_id,
                            platform=platform,
                            external_id=external_id,
                            role="admin",
                            is_active=True
                        )
                        session.add(user)
                        logger.info("Seeded new user: {}", user_db_id)
                    else:
                        # Ensure user is active and has correct role
                        user.is_active = True
                        user.role = "admin"
            
            session.commit()

    # --- Knowledge / RAG Methods ---

    def add_knowledge(self, owner_platform: str, owner_id: str, content: str, embedding: list[float], metadata: dict | None = None) -> bool:
        """Add a knowledge snippet with its embedding."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        import json
        with self.SessionLocal() as session:
            snippet = Knowledge(
                owner_id=full_owner_id,
                content=content,
                embedding=embedding,
                metadata_json=json.dumps(metadata or {})
            )
            session.add(snippet)
            session.commit()
            return True

    def search_knowledge(self, owner_platform: str, owner_id: str, embedding: list[float], limit: int = 5) -> list[dict[str, Any]]:
        """Search knowledge using vector similarity."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        import json
        with self.SessionLocal() as session:
            # L2 distance search (can be changed to cosine if needed)
            stmt = select(Knowledge).where(Knowledge.owner_id == full_owner_id).order_by(
                Knowledge.embedding.l2_distance(embedding)
            ).limit(limit)
            
            results = session.execute(stmt).scalars().all()
            return [
                {
                    "content": r.content,
                    "metadata": json.loads(r.metadata_json or "{}"),
                    "created_at": r.created_at.isoformat()
                }
                for r in results
            ]

    # --- Contact Methods ---
    def save_contact(self, owner_platform: str, owner_id: str, name: str, contact_platform: str, external_id: str) -> bool:
        """Save or update a contact for a user."""
        owner_id = self._normalize_id(owner_platform, owner_id)
        external_id = self._normalize_id(contact_platform, external_id)
        full_owner_id = f"{owner_platform}:{owner_id}"
        
        with self.SessionLocal() as session:
            # Check for existing contact with same name for this owner
            stmt = select(Contact).where(Contact.owner_id == full_owner_id, func.lower(Contact.name) == name.lower())
            contact = session.execute(stmt).scalar_one_or_none()
            
            if contact:
                contact.platform = contact_platform
                contact.external_id = external_id
            else:
                contact = Contact(
                    owner_id=full_owner_id,
                    name=name,
                    platform=contact_platform,
                    external_id=external_id
                )
                session.add(contact)
            
            session.commit()
            logger.info("Saved contact '{}' for user {}", name, full_owner_id)
            return True

    def get_contact(self, owner_platform: str, owner_id: str, name: str) -> dict[str, Any] | None:
        """Find a contact by name."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            # Case insensitive search
            stmt = select(Contact).where(Contact.owner_id == full_owner_id, func.lower(Contact.name) == name.lower())
            contact = session.execute(stmt).scalar_one_or_none()
            if contact:
                return {
                    "name": contact.name,
                    "platform": contact.platform,
                    "external_id": contact.external_id
                }
            return None

    def get_contact_by_id(self, owner_platform: str, owner_id: str, platform: str, external_id: str) -> dict[str, Any] | None:
        """Find a contact by their platform identifier (e.g. phone number)."""
        owner_id = self._normalize_id(owner_platform, owner_id)
        external_id = self._normalize_id(platform, external_id)
        full_owner_id = f"{owner_platform}:{owner_id}"
        
        with self.SessionLocal() as session:
            stmt = select(Contact).where(
                Contact.owner_id == full_owner_id, 
                Contact.platform == platform,
                Contact.external_id == external_id
            )
            contact = session.execute(stmt).scalar_one_or_none()
            if contact:
                return {
                    "name": contact.name,
                    "platform": contact.platform,
                    "external_id": contact.external_id
                }
            return None

    def list_contacts(self, owner_platform: str, owner_id: str) -> list[dict[str, Any]]:
        """List all contacts for a user."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            stmt = select(Contact).where(Contact.owner_id == full_owner_id)
            contacts = session.execute(stmt).scalars().all()
            return [
                {
                    "name": c.name,
                    "platform": c.platform,
                    "external_id": c.external_id
                }
                for c in contacts
            ]
    def delete_contact(self, owner_platform: str, owner_id: str, name: str) -> bool:
        """Delete a contact by name."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            stmt = select(Contact).where(Contact.owner_id == full_owner_id, func.lower(Contact.name) == name.lower())
            contact = session.execute(stmt).scalar_one_or_none()
            if contact:
                session.delete(contact)
                session.commit()
                logger.info("Deleted contact '{}' for user {}", name, full_owner_id)
                return True
            return False
    def add_finance_record(self, owner_platform: str, owner_id: str, amount: int, type: str, category: str, description: str = "") -> bool:
        """Add a financial record."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            record = FinanceRecord(
                owner_id=full_owner_id,
                amount=amount,
                type=type,
                category=category,
                description=description
            )
            session.add(record)
            session.commit()
            return True

    def get_finance_summary(self, owner_platform: str, owner_id: str) -> dict[str, Any]:
        """Get summary of income and expenses."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            # Total income
            inc_stmt = select(func.sum(FinanceRecord.amount)).where(FinanceRecord.owner_id == full_owner_id, FinanceRecord.type == "income")
            income = session.execute(inc_stmt).scalar() or 0
            
            # Total expense
            exp_stmt = select(func.sum(FinanceRecord.amount)).where(FinanceRecord.owner_id == full_owner_id, FinanceRecord.type == "expense")
            expense = session.execute(exp_stmt).scalar() or 0
            
            return {
                "total_income": float(income),
                "total_expense": float(expense),
                "balance": float(income - expense)
            }
