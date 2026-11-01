"""Price book for the three models; the APIs expose no reliable cost field.

Values come from ADR-001 (SAM, $0.20 per 1,000 frames), ADR-002 (Wonder, $4/$20 per
1M tokens) and ADR-003/TRD §2 (Muse Image, $0.01 per image). The ledger prices usage
itself so `replay`/`demo` runs, which spend nothing, still produce a comparable report.
"""

from __future__ import annotations

from dataclasses import dataclass

WONDER_MODEL = "muse-wonder-1.0"
IMAGE_MODEL = "muse-image-1.0"
SAM_MODEL = "sam-3.1"


@dataclass(frozen=True, slots=True)
class Price:
    input_per_million: float = 0.0
    output_per_million: float = 0.0
    per_image: float = 0.0
    per_frame: float = 0.0

    def usd(
        self, *, tokens_in: int = 0, tokens_out: int = 0, images: int = 0, frames: int = 0
    ) -> float:
        return (
            tokens_in * self.input_per_million / 1_000_000
            + tokens_out * self.output_per_million / 1_000_000
            + images * self.per_image
            + frames * self.per_frame
        )


PRICES: dict[str, Price] = {
    WONDER_MODEL: Price(input_per_million=4.0, output_per_million=20.0),
    IMAGE_MODEL: Price(per_image=0.01),
    SAM_MODEL: Price(per_frame=0.0002),
}

ESTIMATED_CALL_USD: dict[str, float] = {
    WONDER_MODEL: 0.05,
    IMAGE_MODEL: 0.01,
    SAM_MODEL: 0.25,
}
"""Conservative reservation per call; the ledger settles the measured amount."""


def usd_for(
    model: str, *, tokens_in: int = 0, tokens_out: int = 0, images: int = 0, frames: int = 0
) -> float:
    price = PRICES.get(model)
    if price is None:
        return 0.0
    return round(
        price.usd(tokens_in=tokens_in, tokens_out=tokens_out, images=images, frames=frames), 8
    )


__all__ = [
    "ESTIMATED_CALL_USD",
    "IMAGE_MODEL",
    "PRICES",
    "SAM_MODEL",
    "WONDER_MODEL",
    "Price",
    "usd_for",
]
