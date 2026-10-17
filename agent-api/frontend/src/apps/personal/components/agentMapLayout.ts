/** Shared row layout: adding an agent must never place it on an existing node. */
type LayoutNode = {id: string; kind: string};
const AGENT_ORDER = ['market', 'invoices', 'vacation', 'telegram', 'mywellness', 'garden', 'music'];
const PLATFORM_ORDER = ['scheduler', 'messaging', 'household'];
const SERVICE_ORDER = ['openai', 'database', 'homeassistant'];
const NODE_WIDTH = 218;
const CENTER_X = 600;

export function positionsForNodes(nodes: readonly LayoutNode[]): Record<string, {x: number; y: number}> {
    const result: Record<string, {x: number; y: number}> = {};
    const sorted = (items: LayoutNode[], order: string[]) => [...items].sort((a, b) => {
        const ai = order.indexOf(a.id), bi = order.indexOf(b.id);
        return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi) || a.id.localeCompare(b.id);
    });
    const row = (items: LayoutNode[], y: number, spacing: number) => items.forEach((node, i) => {
        result[node.id] = {x: CENTER_X - NODE_WIDTH / 2 + (i - (items.length - 1) / 2) * spacing, y};
    });
    const orchestrators = nodes.filter(n => n.kind === 'orchestrator');
    const platforms = nodes.filter(n => PLATFORM_ORDER.includes(n.id) || n.kind === 'platform');
    const agents = sorted(nodes.filter(n => n.kind === 'agent' && !PLATFORM_ORDER.includes(n.id)), AGENT_ORDER);
    const remaining = sorted(nodes.filter(n => !orchestrators.includes(n) && !platforms.includes(n) && !agents.includes(n)), SERVICE_ORDER);
    row(orchestrators, 20, 320);
    row(sorted(platforms, PLATFORM_ORDER), 190, 320);
    const rows = Math.ceil(agents.length / 4);
    for (let i = 0; i < rows; i++) row(agents.slice(i * 4, i * 4 + 4), 390 + i * 150, 280);
    for (let i = 0; i < Math.ceil(remaining.length / 4); i++) row(remaining.slice(i * 4, i * 4 + 4), 470 + rows * 150 + i * 150, 320);
    return result;
}
