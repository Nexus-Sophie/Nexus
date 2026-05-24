from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.postgres.models import (
    FeatureItemRecord,
    FeatureItemStatus,
    FeatureRecord,
    ProductProposalRecord,
)


@dataclass(frozen=True)
class FeatureItemDispatchGroup:
    """Workflow-specific scheduling key for feature-item publishing.

    Product workflow uses the same `(user_id, repo, project)` ownership boundary
    as agent selection. Keep this scheduling shape close to the product workflow
    service instead of the generic feature-item repository.
    """

    user_id: uuid.UUID
    repo: str | None
    project: str | None


async def list_pending_dispatch_groups(session: AsyncSession) -> list[FeatureItemDispatchGroup]:
    """List pending workflow groups in oldest-item-first order.

    One blocked workspace should not stall unrelated users or repositories.
    Group pending items by the same `(user_id, repo, project)` key that agent
    selection uses, then let the poller publish at most one item per group
    during a round before looping again.
    """
    query = (
        select(
            ProductProposalRecord.user_id,
            ProductProposalRecord.repo,
            ProductProposalRecord.project,
        )
        .join(FeatureRecord, FeatureRecord.proposal_id == ProductProposalRecord.id)
        .join(FeatureItemRecord, FeatureItemRecord.feature_id == FeatureRecord.id)
        .where(
            FeatureItemRecord.task_id.is_(None),
            FeatureItemRecord.status == FeatureItemStatus.pending,
        )
        .group_by(
            ProductProposalRecord.user_id,
            ProductProposalRecord.repo,
            ProductProposalRecord.project,
        )
        .order_by(
            func.min(FeatureItemRecord.created_at).asc(),
            func.min(FeatureRecord.created_at).asc(),
        )
    )
    result = await session.execute(query)
    return [
        FeatureItemDispatchGroup(user_id=user_id, repo=repo, project=project)
        for user_id, repo, project in result.all()
    ]


async def get_next_unassigned_for_dispatch_group(
    session: AsyncSession,
    *,
    dispatch_group: FeatureItemDispatchGroup,
) -> FeatureItemRecord | None:
    """Return the next pending feature item for one workflow dispatch group."""
    query = (
        select(FeatureItemRecord)
        .join(FeatureRecord, FeatureItemRecord.feature_id == FeatureRecord.id)
        .join(ProductProposalRecord, FeatureRecord.proposal_id == ProductProposalRecord.id)
        .where(
            ProductProposalRecord.user_id == dispatch_group.user_id,
            ProductProposalRecord.repo == dispatch_group.repo,
            ProductProposalRecord.project == dispatch_group.project,
            FeatureItemRecord.task_id.is_(None),
            FeatureItemRecord.status == FeatureItemStatus.pending,
        )
        .order_by(
            FeatureItemRecord.created_at.asc(),
            FeatureRecord.created_at.asc(),
            FeatureItemRecord.order_index.asc(),
        )
        .limit(1)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()
