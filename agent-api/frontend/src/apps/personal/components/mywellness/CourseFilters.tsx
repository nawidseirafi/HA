export type CourseFilter = 'today' | 'tomorrow' | 'dayAfterTomorrow';

interface Props {
  value: CourseFilter;
  onChange: (value: CourseFilter) => void;
}

const filters: Array<{ value: CourseFilter; label: string }> = [
  { value: 'today', label: 'Heute' },
  { value: 'tomorrow', label: 'Morgen' },
  { value: 'dayAfterTomorrow', label: 'Übermorgen' },
];

export function CourseFilters({ value, onChange }: Props) {
  return (
    <div className="course-filters" role="tablist" aria-label="Kursfilter">
      {filters.map((filter) => (
        <button
          className={value === filter.value ? 'active' : ''}
          key={filter.value}
          type="button"
          onClick={() => onChange(filter.value)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
