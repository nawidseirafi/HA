import type { Course } from '../../api/client';
import { courseDayKey } from './courseFormat';

export type WellnessDay = 'today' | 'tomorrow' | 'dayAfterTomorrow';

const labels: Record<WellnessDay, string> = {
  today: 'Heute',
  tomorrow: 'Morgen',
  dayAfterTomorrow: 'Übermorgen',
};

export function WellnessDaySelector({ value, courses, onChange }: { value: WellnessDay; courses: Course[]; onChange: (value: WellnessDay) => void }) {
  const days = Object.keys(labels) as WellnessDay[];
  return (
    <div className="wellness-day-selector">
      {days.map((day) => {
        const count = courses.filter((course) => courseDayKey(course.startTime ?? course.starts_at) === day).length;
        return (
          <button className={value === day ? 'active' : ''} type="button" onClick={() => onChange(day)} key={day}>
            <span>{labels[day]}</span>
            <b>{count}</b>
          </button>
        );
      })}
    </div>
  );
}
