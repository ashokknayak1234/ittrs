export const flag = value => value === true || value === 1;
export function filterTickets(tickets, query, filter) {
  const term = query.trim().toLocaleLowerCase();
  return tickets.filter(ticket => {
    const matchesText = [ticket.id,ticket.complaint_text,ticket.category,ticket.team,ticket.severity,ticket.override_reason].map(v=>String(v??'')).join(' ').toLocaleLowerCase().includes(term);
    const matchesFilter = filter === 'all' || (filter === 'alerts' ? flag(ticket.sla_alerted) : filter === 'unsatisfied' ? ticket.satisfaction_status === 'Not_Satisfied' : ticket.severity === filter);
    return matchesText && matchesFilter;
  });
}
export const settingsGroups = {
  severity_sla_hours: 'Resolution target · hours',
  category_multipliers: 'Category multipliers',
  risk_thresholds_hours: 'Risk thresholds · hours',
  workload_bump_threshold: 'Workload threshold'
};
