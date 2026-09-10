"""
Shim module for app.skw.repositories.knowledge_object_repo
Re-exports KnowledgeObjectRepository from app.repositories.knowledge_object_repo
"""

from app.repositories.knowledge_object_repo import KnowledgeObjectRepository

__all__ = ["KnowledgeObjectRepository"]
