/**
 * Polygon simplification for the overlay (03_UI_Spec §7: tolerance 1.5 px at 720p).
 *
 * Ramer–Douglas–Peucker in pixel space; the caller projects normalised coordinates
 * first so the tolerance means something on screen.
 */

export type Point = [number, number];

function squareDistanceToSegment(point: Point, start: Point, end: Point): number {
  const [px, py] = point;
  const [ax, ay] = start;
  const [bx, by] = end;
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return (px - ax) ** 2 + (py - ay) ** 2;

  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return (px - cx) ** 2 + (py - cy) ** 2;
}

function rdp(points: Point[], budget: number): Point[] {
  if (points.length <= 2) return points;

  const first = points[0] as Point;
  const last = points[points.length - 1] as Point;

  let farthest = -1;
  let farthestDistance = 0;
  for (let index = 1; index < points.length - 1; index += 1) {
    const distance = squareDistanceToSegment(points[index] as Point, first, last);
    if (distance > farthestDistance) {
      farthestDistance = distance;
      farthest = index;
    }
  }

  if (farthest === -1 || farthestDistance <= budget) return [first, last];

  const left = rdp(points.slice(0, farthest + 1), budget);
  const right = rdp(points.slice(farthest), budget);
  return [...left.slice(0, -1), ...right];
}

function withoutRepeats(points: Point[]): Point[] {
  return points.filter((point, index) => {
    const previous = points[index - 1];
    return previous === undefined || previous[0] !== point[0] || previous[1] !== point[1];
  });
}

/** Simplify a ring; a drawable result always keeps at least three points. */
export function simplifyPolygon(points: Point[], tolerance: number): Point[] {
  if (points.length <= 3) return points;

  const simplified = withoutRepeats(rdp(points, tolerance * tolerance));
  if (simplified.length >= 3) return simplified;

  const middle = points[Math.floor(points.length / 2)] as Point;
  return [points[0] as Point, middle, points[points.length - 1] as Point];
}
