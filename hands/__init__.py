"""hands: execution tickets for the external agent browser.

social-agent proposes, gates, and logs. The agent's browser performs.
See hands/HANDS.md for the protocol and hands/tickets.py for the API.
"""

from hands.tickets import (
    TICKET_ACTIONS,
    TicketRefused,
    cancel_ticket,
    create_ticket,
    fulfill_ticket,
    get_ticket,
    list_tickets,
)

__all__ = [
    "TICKET_ACTIONS",
    "TicketRefused",
    "cancel_ticket",
    "create_ticket",
    "fulfill_ticket",
    "get_ticket",
    "list_tickets",
]
