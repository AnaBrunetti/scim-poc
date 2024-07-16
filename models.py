from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import db
from datetime import datetime

# Define a many-to-many relationship
links = db.Table(
    "link",
    db.Column(
        "group_id", UUID(as_uuid=True), db.ForeignKey("groups.id"), primary_key=True
    ),
    db.Column(
        "user_id", UUID(as_uuid=True), db.ForeignKey("users.id"), primary_key=True
    ),
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    active = db.Column(db.Boolean)
    userName = db.Column(db.String(), unique=True, nullable=False)
    givenName = db.Column(db.String())
    middleName = db.Column(db.String())
    familyName = db.Column(db.String())
    groups = db.relationship(
        "Group",
        secondary=links,
        lazy="subquery",
        backref=db.backref("users", lazy=True),
    )
    emails_primary = db.Column(db.Boolean)
    emails_value = db.Column(db.String())
    emails_type = db.Column(db.String())
    displayName = db.Column(db.String())
    locale = db.Column(db.String())
    externalId = db.Column(db.String(), unique=True)
    password = db.Column(db.String())
    created = db.Column(db.DateTime, default=datetime.utcnow)
    updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, active, userName, givenName, middleName, familyName, emails_primary, emails_value, emails_type, displayName, locale, externalId, password):
        self.active = active
        self.userName = userName
        self.givenName = givenName
        self.middleName = middleName
        self.familyName = familyName
        self.emails_primary = emails_primary
        self.emails_value = emails_value
        self.emails_type = emails_type
        self.displayName = displayName
        self.locale = locale
        self.externalId = externalId
        self.password = password

    def __repr__(self):
        return f"<id {self.id}>"

    def serialize(self):
        created_iso = self.created.isoformat() + "Z" if self.created else None
        updated_iso = self.updated.isoformat() + "Z" if self.updated else None
        
        # Verifica se o e-mail é válido e preenche com default caso necessário
        emails = [{
            "value": self.emails_value or self.userName,
            "type": self.emails_type or "work",
            "primary": self.emails_primary if self.emails_primary is not None else True
        }]
        
        # Preenche o campo name com dados padrão se não estiver completamente preenchido
        name = {
            "formatted": self.givenName or "",
            "familyName": self.familyName or "",
            "middleName": self.middleName or ""
        }
        
        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "id": str(self.id),
            "externalId": self.externalId,
            "meta": {
                "resourceType": "User",
                "created": created_iso,
                "lastModified": updated_iso
            },
            "userName": self.userName,
            "name": name,
            "active": self.active,
            "emails": emails,
            "displayName": self.displayName or self.userName  # Use userName as fallback for displayName
        }

class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    displayName = db.Column(db.String(), unique=True)
    externalId = db.Column(db.String(), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Adicionando created_at
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Adicionando updated_at

    def serialize(self, include_members=True):
        users = []
        if include_members:
            users = [{"value": str(user.id), "display": user.userName, "$ref": f"https://your-scim-endpoint/scim/v2/Users/{str(user.id)}"} for user in self.users]

        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "id": str(self.id),
            "externalId": self.externalId,
            "meta": {
                "resourceType": "Group",
                "created": self.created_at.isoformat() if self.created_at else None,
                "lastModified": self.updated_at.isoformat() if self.updated_at else None
            },
            "displayName": self.displayName,
            "members": users,
        }
