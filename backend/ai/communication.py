"""
backend/ai/communication.py
─────────────────────────────
Agent Communication Infrastructure
Enables true agentic collaboration through message passing and shared goals.

Design Principles:
1. Loose coupling - agents don't need direct references to each other
2. Persistent messaging - survives process restarts (uses database)
3. Goal-oriented - supports multi-step agent collaborations
4. Observable - all communication is traceable for debugging/optimization
5. Enterprise-ready - supports multi-tenancy, security, and auditing
"""

import json
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, ForeignKey, Index, UniqueConstraint
import logging

logger = logging.getLogger("ai.communication")

from models import Base


class MessageType(str, Enum):
    """Standard message types for agent communication"""
    REQUEST = "request"          # Agent asking another agent to do something
    RESPONSE = "response"        # Response to a request
    PROPOSE = "propose"          # Suggest a course of action
    AGREE = "agree"              # Agreement with a proposal
    DISAGREE = "disagree"        # Disagreement with reasoning
    INFORM = "inform"            # Sharing information (no action required)
    ALERT = "alert"              # Urgent information requiring attention
    GOAL = "goal"                # Setting or updating a shared goal
    PLAN = "plan"                # Sharing a plan for achieving a goal
    RESULT = "result"            # Sharing outcome of an action
    QUERY = "query"              # Asking for information
    COMMAND = "command"          # Directing another agent to perform action


class Priority(str, Enum):
    """Message priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentCommunicationMessage(Base):
    """
    Database model for persistent agent communication
    Using PostgreSQL for reliability and querying capabilities
    """
    __tablename__ = 'agent_communication'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=False, index=True)  # Multi-tenancy

    # Message routing
    sender_agent = Column(String, nullable=False, index=True)
    recipient_agent = Column(String, nullable=True, index=True)  # None = broadcast
    message_type = Column(String, nullable=False, index=True)
    priority = Column(String, nullable=False, default=Priority.MEDIUM)

    # Message content
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=False)  # JSON serialized payload
    correlation_id = Column(String, nullable=True, index=True)  # For tracking conversations
    reply_to = Column(String, nullable=True, index=True)  # Reference to parent message

    # Lifecycle
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    is_processed = Column(Boolean, default=False, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(String, nullable=True)  # Which agent processed it

    # Observability
    trace_id = Column(String, nullable=True, index=True)  # For distributed tracing
    span_id = Column(String, nullable=True, index=True)

    __table_args__ = (
        Index('idx_agent_communication_tenant_type_time', 'tenant_id', 'message_type', 'timestamp'),
        Index('idx_agent_communication_unprocessed', 'tenant_id', 'is_processed', 'timestamp'),
    )


class AgentCapability(str, Enum):
    """Standard capabilities that agents can advertise"""
    # Intelligence capabilities
    PRICING_ANALYSIS = "pricing.analysis"
    PROFIT_ANALYSIS = "profit.analysis"
    INVENTORY_PREDICTION = "inventory.prediction"
    REVENUE_FORECASTING = "revenue.forecasting"
    MENU_ENGINEERING = "menu.engineering"
    RESERVATION_OPTIMIZATION = "reservation.optimization"
    LABOR_OPTIMIZATION = "labor.optimization"
    SUPPLY_CHAIN_ANALYSIS = "supply.chain.analysis"
    KDS_INTELLIGENCE = "kds.intelligence"
    MARKETING_INTELLIGENCE = "marketing.intelligence"

    # Communication capabilities
    WHATSAPP_MESSAGING = "whatsapp.messaging"
    EMAIL_MESSAGING = "email.messaging"
    SMS_MESSAGING = "sms.messaging"

    # Action capabilities
    DATABASE_UPDATE = "database.update"
    EXTERNAL_API_CALL = "external.api.call"
    FILE_OPERATION = "file.operation"
    SCHEDULED_TASK = "scheduled.task"

    # Meta capabilities
    GOAL_PLANNING = "goal.planning"
    REASONING = "reasoning"
    LEARNING = "learning"


class AgentInfo(Base):
    """
    Registry of agents in the system
    """
    __tablename__ = 'agent_registry'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'agent_id', name='uix_tenant_agent_id'),
        Index('idx_agent_registry_tenant_active', 'tenant_id', 'is_active')
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=False, index=True)

    # Agent identification
    agent_id = Column(String, nullable=False, index=True)  # e.g., "pricing_intelligence_v1"
    agent_name = Column(String, nullable=False)
    agent_version = Column(String, nullable=False)

    # Capabilities and metadata
    capabilities = Column(Text, nullable=False)  # JSON array of AgentCapability
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Lifecycle
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_heartbeat = Column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)

    # Configuration
    config = Column(Text, nullable=True)  # JSON configuration for the agent


class CommunicationHub:
    """
    Central hub for agent communication
    Provides publish/subscribe, message persistence, and agent discovery
    """

    def __init__(self, db_session: Session, tenant_id: str):
        self.db = db_session
        self.tenant_id = tenant_id
        self._local_handlers: Dict[str, List[Callable]] = {}  # In-process handlers for performance
        logger.info(f"[CommunicationHub] Initialized for tenant {tenant_id}")

    def register_agent(self, agent_id: str, agent_name: str, capabilities: List[AgentCapability],
                      version: str = "1.0.0", description: str = "", config: Optional[Dict] = None) -> str:
        """
        Register an agent in the system
        Returns the agent registry ID
        """
        try:
            # Check if agent already exists
            existing = self.db.query(AgentInfo).filter(
                AgentInfo.tenant_id == self.tenant_id,
                AgentInfo.agent_id == agent_id
            ).first()

            if existing:
                # Update existing registration
                existing.agent_name = agent_name
                existing.agent_version = version
                existing.description = description
                existing.capabilities = json.dumps([c.value for c in capabilities])
                existing.config = json.dumps(config) if config else None
                existing.last_heartbeat = datetime.utcnow()
                existing.is_active = True
                agent_record = existing
                logger.info(f"[CommunicationHub] Updated agent registration: {agent_id}")
            else:
                # Create new registration
                agent_record = AgentInfo(
                    tenant_id=self.tenant_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    agent_version=version,
                    description=description,
                    capabilities=json.dumps([c.value for c in capabilities]),
                    config=json.dumps(config) if config else None,
                    is_active=True
                )
                self.db.add(agent_record)
                logger.info(f"[CommunicationHub] Registered new agent: {agent_id}")

            self.db.commit()
            return str(agent_record.id)

        except Exception as e:
            self.db.rollback()
            logger.error(f"[CommunicationHub] Failed to register agent {agent_id}: {e}")
            raise

    def heartbeat(self, agent_id: str):
        """Update agent's last seen timestamp"""
        try:
            agent = self.db.query(AgentInfo).filter(
                AgentInfo.tenant_id == self.tenant_id,
                AgentInfo.agent_id == agent_id
            ).first()

            if agent:
                agent.last_heartbeat = datetime.utcnow()
                agent.last_seen = datetime.utcnow()
                self.db.commit()
        except Exception as e:
            logger.error(f"[CommunicationHub] Heartbeat failed for {agent_id}: {e}")
            self.db.rollback()

    def send_message(self, sender_agent: str, message_type: MessageType,
                    body: Dict[str, Any], recipient_agent: Optional[str] = None,
                    priority: Priority = Priority.MEDIUM,
                    correlation_id: Optional[str] = None,
                    reply_to: Optional[str] = None,
                    trace_id: Optional[str] = None,
                    span_id: Optional[str] = None,
                    ttl_minutes: int = 60) -> str:
        """
        Send a message to another agent or broadcast
        Returns the message ID
        """
        try:
            message = AgentCommunicationMessage(
                tenant_id=self.tenant_id,
                sender_agent=sender_agent,
                recipient_agent=recipient_agent,
                message_type=message_type.value,
                priority=priority.value,
                subject=body.get('subject', ''),
                body=json.dumps(body),
                correlation_id=correlation_id,
                reply_to=reply_to,
                trace_id=trace_id,
                span_id=span_id,
                expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes)
            )

            self.db.add(message)
            self.db.commit()

            # Also notify local handlers for immediate processing (performance)
            self._notify_local_handlers(message)

            logger.debug(f"[CommunicationHub] Sent {message_type.value} from {sender_agent} "
                        f"{'to ' + recipient_agent if recipient_agent else 'to all'} "
                        f"(msg_id: {message.id})")

            return str(message.id)

        except Exception as e:
            self.db.rollback()
            logger.error(f"[CommunicationHub] Failed to send message: {e}")
            raise

    def receive_messages(self, agent_id: str, message_types: Optional[List[MessageType]] = None,
                        limit: int = 100, mark_processed: bool = True) -> List[Dict]:
        """
        Receive messages for this agent
        Returns list of message dictionaries
        """
        try:
            query = self.db.query(AgentCommunicationMessage).filter(
                AgentCommunicationMessage.tenant_id == self.tenant_id,
                AgentCommunicationMessage.recipient_agent.in_([agent_id, None]),  # Messages to this agent or broadcasts
                AgentCommunicationMessage.is_processed == False,
                AgentCommunicationMessage.expires_at > datetime.utcnow()  # Not expired
            ).order_by(AgentCommunicationMessage.timestamp.desc())

            if message_types:
                type_values = [mt.value for mt in message_types]
                query = query.filter(AgentCommunicationMessage.message_type.in_(type_values))

            messages = query.limit(limit).all()

            result = []
            for msg in messages:
                try:
                    msg_dict = {
                        'id': msg.id,
                        'sender': msg.sender_agent,
                        'type': msg.message_type,
                        'priority': msg.priority,
                        'subject': msg.subject,
                        'body': json.loads(msg.body),
                        'timestamp': msg.timestamp,
                        'correlation_id': msg.correlation_id,
                        'reply_to': msg.reply_to,
                        'trace_id': msg.trace_id,
                        'span_id': msg.span_id
                    }
                    result.append(msg_dict)

                    if mark_processed:
                        msg.is_processed = True
                        msg.processed_at = datetime.utcnow()
                        msg.processed_by = agent_id

                except json.JSONDecodeError:
                    logger.error(f"[CommunicationHub] Failed to decode message body: {msg.id}")
                    continue

            if mark_processed and result:
                self.db.commit()

            return result

        except Exception as e:
            self.db.rollback()
            logger.error(f"[CommunicationHub] Failed to receive messages: {e}")
            raise

    def subscribe_local(self, message_type: MessageType, handler: Callable[[Dict], None]):
        """
        Subscribe to messages for immediate in-process handling
        Use for low-latency requirements within the same process
        """
        key = message_type.value
        if key not in self._local_handlers:
            self._local_handlers[key] = []
        self._local_handlers[key].append(handler)
        logger.debug(f"[CommunicationHub] Local subscription to {key}")

    def _notify_local_handlers(self, message: AgentCommunicationMessage):
        """Notify local in-process handlers"""
        try:
            # Check for specific message type handlers
            handlers = self._local_handlers.get(message.message_type, [])
            # Also check for wildcard handlers
            handlers.extend(self._local_handlers.get('*', []))

            msg_dict = {
                'id': message.id,
                'sender': message.sender_agent,
                'type': message.message_type,
                'priority': message.priority,
                'subject': message.subject,
                'body': json.loads(message.body),
                'timestamp': message.timestamp,
                'correlation_id': message.correlation_id,
                'reply_to': message.reply_to,
                'trace_id': message.trace_id,
                'span_id': message.span_id
            }

            for handler in handlers:
                try:
                    handler(msg_dict)
                except Exception as e:
                    logger.error(f"[CommunicationHub] Local handler failed: {e}")

        except json.JSONDecodeError:
            logger.error(f"[CommunicationHub] Failed to decode message for local handlers: {message.id}")

    def get_agent_capabilities(self, agent_id: str) -> List[AgentCapability]:
        """Get capabilities for a specific agent"""
        try:
            agent = self.db.query(AgentInfo).filter(
                AgentInfo.tenant_id == self.tenant_id,
                AgentInfo.agent_id == agent_id,
                AgentInfo.is_active == True
            ).first()

            if agent:
                return [AgentCapability(c) for c in json.loads(agent.capabilities)]
            return []

        except Exception as e:
            logger.error(f"[CommunicationHub] Failed to get capabilities for {agent_id}: {e}")
            return []

    def find_agents_by_capability(self, capability: AgentCapability) -> List[Dict]:
        """Find all agents with a specific capability"""
        try:
            agents = self.db.query(AgentInfo).filter(
                AgentInfo.tenant_id == self.tenant_id,
                AgentInfo.is_active == True,
                AgentInfo.capabilities.like(f'%"{capability.value}"%')
            ).all()

            return [
                {
                    'id': agent.agent_id,
                    'name': agent.agent_name,
                    'version': agent.agent_version,
                    'capabilities': json.loads(agent.capabilities),
                    'last_seen': agent.last_seen
                }
                for agent in agents
            ]

        except Exception as e:
            logger.error(f"[CommunicationHub] Failed to find agents by capability {capability}: {e}")
            return []

    def get_conversation_thread(self, correlation_id: str) -> List[Dict]:
        """Get all messages in a conversation thread"""
        try:
            messages = self.db.query(AgentCommunicationMessage).filter(
                AgentCommunicationMessage.tenant_id == self.tenant_id,
                AgentCommunicationMessage.correlation_id == correlation_id
            ).order_by(AgentCommunicationMessage.timestamp.asc()).all()

            return [
                {
                    'id': msg.id,
                    'sender': msg.sender_agent,
                    'recipient': msg.recipient_agent,
                    'type': msg.message_type,
                    'body': json.loads(msg.body),
                    'timestamp': msg.timestamp,
                    'processed': msg.is_processed
                }
                for msg in messages
            ]

        except Exception as e:
            logger.error(f"[CommunicationHub] Failed to get conversation thread {correlation_id}: {e}")
            return []


# Global communication hub instance (tenant-specific)
_communication_hubs: Dict[str, CommunicationHub] = {}


def get_communication_hub(db_session: Session, tenant_id: str) -> CommunicationHub:
    """Get or create communication hub for a tenant"""
    if tenant_id not in _communication_hubs:
        _communication_hubs[tenant_id] = CommunicationHub(db_session, tenant_id)
    return _communication_hubs[tenant_id]


def cleanup_expired_messages(db_session: Session, tenant_id: str, older_than_hours: int = 24):
    """Cleanup expired messages (maintenance task)"""
    try:
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        deleted = db_session.query(AgentCommunicationMessage).filter(
            AgentCommunicationMessage.tenant_id == tenant_id,
            AgentCommunicationMessage.timestamp < cutoff,
            AgentCommunicationMessage.is_processed == True
        ).delete()

        db_session.commit()
        logger.info(f"[CommunicationHub] Cleaned up {deleted} expired messages for tenant {tenant_id}")
        return deleted

    except Exception as e:
        db_session.rollback()
        logger.error(f"[CommunicationHub] Failed to cleanup messages: {e}")
        raise