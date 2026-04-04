"""Neo4j loader — MERGE nodes and relationships for graph queries."""

import logging

from neo4j import AsyncSession

from uvo_pipeline.models import CanonicalNotice, CanonicalProcurer, CanonicalSupplier

logger = logging.getLogger(__name__)


async def ensure_constraints(session: AsyncSession) -> None:
    """Create Neo4j constraints and indexes (idempotent)."""
    constraints = [
        "CREATE CONSTRAINT procurer_ico IF NOT EXISTS FOR (p:Procurer) REQUIRE p.ico IS UNIQUE",
        "CREATE CONSTRAINT supplier_ico IF NOT EXISTS FOR (s:Supplier) REQUIRE s.ico IS UNIQUE",
        "CREATE CONSTRAINT cpv_code IF NOT EXISTS FOR (c:CPVCode) REQUIRE c.code IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX notice_pub_date IF NOT EXISTS FOR (n:Notice) ON (n.publication_date)",
        "CREATE INDEX notice_value IF NOT EXISTS FOR (n:Notice) ON (n.final_value)",
        "CREATE INDEX procurer_slug IF NOT EXISTS FOR (p:Procurer) ON (p.name_slug)",
        "CREATE INDEX supplier_slug IF NOT EXISTS FOR (s:Supplier) ON (s.name_slug)",
    ]
    for stmt in constraints + indexes:
        await session.run(stmt)
    logger.info("Neo4j constraints and indexes ensured")


async def merge_procurer_node(session: AsyncSession, procurer: CanonicalProcurer) -> None:
    """MERGE a Procurer node by ico (preferred) or name_slug fallback."""
    if procurer.ico:
        await session.run(
            """
            MERGE (p:Procurer {ico: $ico})
            ON CREATE SET p.name = $name, p.name_slug = $name_slug,
                          p.organisation_type = $org_type, p.country_code = $country
            ON MATCH SET  p.name = $name, p.organisation_type = $org_type
            """,
            ico=procurer.ico,
            name=procurer.name,
            name_slug=procurer.name_slug,
            org_type=procurer.organisation_type,
            country=procurer.country_code,
        )
    else:
        await session.run(
            """
            MERGE (p:Procurer {name_slug: $name_slug})
            ON CREATE SET p.name = $name, p.country_code = $country
            ON MATCH SET  p.name = $name
            """,
            name_slug=procurer.name_slug,
            name=procurer.name,
            country=procurer.country_code,
        )


async def merge_supplier_node(session: AsyncSession, supplier: CanonicalSupplier) -> None:
    """MERGE a Supplier node by ico (preferred) or name_slug fallback."""
    if supplier.ico:
        await session.run(
            """
            MERGE (s:Supplier {ico: $ico})
            ON CREATE SET s.name = $name, s.name_slug = $name_slug, s.country_code = $country
            ON MATCH SET  s.name = $name
            """,
            ico=supplier.ico,
            name=supplier.name,
            name_slug=supplier.name_slug,
            country=supplier.country_code,
        )
    else:
        await session.run(
            """
            MERGE (s:Supplier {name_slug: $name_slug})
            ON CREATE SET s.name = $name, s.country_code = $country
            ON MATCH SET  s.name = $name
            """,
            name_slug=supplier.name_slug,
            name=supplier.name,
            country=supplier.country_code,
        )


async def merge_notice_node(session: AsyncSession, notice: CanonicalNotice) -> None:
    """MERGE a Notice node by (source, source_id)."""
    await session.run(
        """
        MERGE (n:Notice {source: $source, source_id: $source_id})
        ON CREATE SET n.notice_type = $notice_type, n.title = $title,
                      n.publication_date = date($pub_date),
                      n.estimated_value = $est_value, n.final_value = $fin_value,
                      n.currency = $currency, n.status = $status,
                      n.cpv_code = $cpv_code
        ON MATCH SET  n.title = $title, n.status = $status,
                      n.final_value = $fin_value
        """,
        source=notice.source,
        source_id=notice.source_id,
        notice_type=notice.notice_type,
        title=notice.title,
        pub_date=notice.publication_date.isoformat() if notice.publication_date else None,
        est_value=notice.estimated_value,
        fin_value=notice.final_value,
        currency=notice.currency,
        status=notice.status,
        cpv_code=notice.cpv_code,
    )


async def merge_relationships(session: AsyncSession, notice: CanonicalNotice) -> None:
    """Create all relationships for a notice in one transaction."""
    # Procurer -> Notice
    if notice.procurer:
        await merge_procurer_node(session, notice.procurer)
        if notice.procurer.ico:
            await session.run(
                """
                MATCH (p:Procurer {ico: $ico})
                MATCH (n:Notice {source: $source, source_id: $source_id})
                MERGE (p)-[:ISSUED]->(n)
                """,
                ico=notice.procurer.ico,
                source=notice.source,
                source_id=notice.source_id,
            )
        else:
            await session.run(
                """
                MATCH (p:Procurer {name_slug: $name_slug})
                MATCH (n:Notice {source: $source, source_id: $source_id})
                MERGE (p)-[:ISSUED]->(n)
                """,
                name_slug=notice.procurer.name_slug,
                source=notice.source,
                source_id=notice.source_id,
            )

    # Notice -> Supplier (awards)
    for award in notice.awards:
        await merge_supplier_node(session, award.supplier)
        match_field = "ico" if award.supplier.ico else "name_slug"
        match_value = award.supplier.ico if award.supplier.ico else award.supplier.name_slug
        await session.run(
            f"""
            MATCH (s:Supplier {{{match_field}: $match_value}})
            MATCH (n:Notice {{source: $source, source_id: $source_id}})
            MERGE (n)-[r:AWARDED_TO]->(s)
            ON CREATE SET r.value = $value, r.currency = $currency,
                          r.award_date = date($award_date)
            """,
            match_value=match_value,
            source=notice.source,
            source_id=notice.source_id,
            value=award.value,
            currency=award.currency,
            award_date=award.signing_date.isoformat() if award.signing_date else None,
        )

    # Notice -> CPVCode
    if notice.cpv_code:
        await session.run(
            """
            MERGE (c:CPVCode {code: $code})
            WITH c
            MATCH (n:Notice {source: $source, source_id: $source_id})
            MERGE (n)-[:CLASSIFIED_BY]->(c)
            """,
            code=notice.cpv_code,
            source=notice.source,
            source_id=notice.source_id,
        )


async def merge_notice_batch(
    session: AsyncSession,
    notices: list[CanonicalNotice],
) -> dict[str, int]:
    """Merge a batch of notices into Neo4j. Returns {merged, errors}."""
    merged = errors = 0
    for notice in notices:
        try:
            await merge_notice_node(session, notice)
            await merge_relationships(session, notice)
            merged += 1
        except Exception as exc:
            logger.error("Neo4j merge failed for %s/%s: %s", notice.source, notice.source_id, exc)
            errors += 1
    return {"merged": merged, "errors": errors}
