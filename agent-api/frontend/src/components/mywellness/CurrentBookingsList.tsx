import type { MyWellnessCourse } from '../../api/client';
import { CourseList } from './CourseList';

interface Props {
  bookings: MyWellnessCourse[];
}

export function CurrentBookingsList({ bookings }: Props) {
  return (
    <CourseList
      title="Aktuelle Buchungen"
      eyebrow="Bookings"
      courses={bookings}
      emptyText="Keine eingebuchten Kurse aus Agent-Daten erkannt."
    />
  );
}
