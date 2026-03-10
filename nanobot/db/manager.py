"""Database manager forNanobot."""

import os
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import Column, DateTime, String, Boolean, Integer, ForeignKey, create_engine, select, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

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


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String, ForeignKey("users.id"), index=True)
    name = Column(String, index=True)
    platform = Column(String)
    external_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="contacts")


class DatabaseManager:
    """Manages database connection and operations."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables verified/created.")
        except Exception as e:
            logger.error("Failed to create database tables: {}", e)

    def is_allowed(self, platform: str, external_id: str) -> bool:
        """Check if a user is allowed access."""
        with self.SessionLocal() as session:
            stmt = select(User).where(
                User.platform == platform,
                User.external_id == str(external_id),
                User.is_active == True
            )
            user = session.execute(stmt).scalar_one_or_none()
            return user is not None

    def add_user(self, platform: str, external_id: str, role: str = "user") -> bool:
        """Add a new user to the database."""
        with self.SessionLocal() as session:
            # Check if exists
            stmt = select(User).where(User.platform == platform, User.external_id == str(external_id))
            if session.execute(stmt).scalar_one_or_none():
                return False

            user = User(
                id=f"{platform}:{external_id}",
                platform=platform,
                external_id=str(external_id),
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
        """Seed database from config if empty."""
        with self.SessionLocal() as session:
            # Only seed if no users exist
            if session.execute(select(User)).first():
                return

            logger.info("Database empty, seeding users from config...")
            for platform, ids in config_users.items():
                for sid in ids:
                    if sid == "*": continue
                    # Extract numeric ID if sid contains |
                    external_id = sid.split("|")[0]
                    user = User(
                        id=f"{platform}:{external_id}",
                        platform=platform,
                        external_id=external_id,
                        role="admin" # Config users are trusted as admins
                    )
                    session.add(user)
            session.commit()
            logger.info("Database seeded successfully.")

    def save_contact(self, owner_platform: str, owner_id: str, name: str, contact_platform: str, external_id: str) -> bool:
        """Save or update a contact for a user."""
        full_owner_id = f"{owner_platform}:{owner_id}"
        with self.SessionLocal() as session:
            # Check for existing contact with same name for this owner
            stmt = select(Contact).where(Contact.owner_id == full_owner_id, func.lower(Contact.name) == name.lower())
            contact = session.execute(stmt).scalar_one_or_none()
            
            if contact:
                contact.platform = contact_platform
                contact.external_id = str(external_id)
            else:
                contact = Contact(
                    owner_id=full_owner_id,
                    name=name,
                    platform=contact_platform,
                    external_id=str(external_id)
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
