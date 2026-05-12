export const POINTS_BY_POSITION: Record<number, number> = {
  1: 10,
  2: 5,
  3: 3,
};

export function pointsFor(position: number): number {
  return POINTS_BY_POSITION[position] ?? 0;
}

export function positionLabel(position: number): string {
  if (position === 1) return "1st";
  if (position === 2) return "2nd";
  if (position === 3) return "3rd";
  return `${position}th`;
}
