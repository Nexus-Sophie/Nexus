import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Loader2,
  GitMerge,
  GitPullRequest,
  ChevronRight,
  ChevronDown,
  Activity,
  Timer,
  Calendar,
  Search,
  Filter,
  RefreshCw,
  LayoutGrid,
  List,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { mockAgents } from '@/data/mockWorkflows';
import type { Agent, AgentTask, TaskStatus } from '@/types/agent';

// Status configuration with Buildkite-inspired colors
type ExtendedTaskStatus = TaskStatus | 'merged' | 'open' | 'pending' | 'closed';

const statusConfig: Record<ExtendedTaskStatus, {
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
  glowColor?: string;
}> = {
  running: {
    icon: <Loader2 className="h-3.5 w-3.5" />,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    label: 'Running',
    glowColor: 'shadow-amber-500/20',
  },
  waiting: {
    icon: <Clock className="h-3.5 w-3.5" />,
    color: 'text-slate-400',
    bgColor: 'bg-slate-500/10',
    borderColor: 'border-slate-500/30',
    label: 'Waiting',
  },
  completed: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    label: 'Passed',
  },
  failed: {
    icon: <XCircle className="h-3.5 w-3.5" />,
    color: 'text-rose-400',
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-rose-500/30',
    label: 'Failed',
  },
  error: {
    icon: <AlertCircle className="h-3.5 w-3.5" />,
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    label: 'Error',
  },
  // Extended statuses for task categorization
  merged: {
    icon: <GitMerge className="h-3.5 w-3.5" />,
    color: 'text-violet-400',
    bgColor: 'bg-violet-500/10',
    borderColor: 'border-violet-500/30',
    label: 'Merged',
  },
  open: {
    icon: <GitPullRequest className="h-3.5 w-3.5" />,
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    label: 'Open',
  },
  pending: {
    icon: <Clock className="h-3.5 w-3.5" />,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    label: 'Pending',
  },
  closed: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    color: 'text-slate-400',
    bgColor: 'bg-slate-500/10',
    borderColor: 'border-slate-500/30',
    label: 'Closed',
  },
};

const agentStatusConfig = {
  online: { color: 'bg-emerald-500', label: 'Online' },
  busy: { color: 'bg-amber-500', label: 'Busy' },
  offline: { color: 'bg-slate-500', label: 'Offline' },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes < 60) {
    return remaining > 0 ? `${minutes}m ${remaining}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Calculate task category based on task properties
function getTaskCategory(task: AgentTask): ExtendedTaskStatus {
  if (task.status === 'running') return 'running';
  if (task.status === 'waiting') return 'pending';
  if (task.status === 'failed' || task.status === 'error') return 'failed';
  if (task.status === 'completed') {
    // Simulate merged vs closed based on task properties
    return task.metadata?.branch === 'main' ? 'merged' : 'closed';
  }
  return task.status;
}

interface TaskRowProps {
  task: AgentTask;
  onClick: () => void;
}

function TaskRow({ task, onClick }: TaskRowProps) {
  const category = getTaskCategory(task);
  const config = statusConfig[category];
  const isRunning = task.status === 'running';

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full group flex items-center gap-4 px-4 py-3",
        "hover:bg-white/[0.02] transition-colors duration-150",
        "border-b border-white/[0.04] last:border-b-0"
      )}
    >
      {/* Status Indicator */}
      <div className="flex-shrink-0 w-6 flex justify-center">
        {isRunning ? (
          <div className="relative">
            <span className="absolute inset-0 animate-ping rounded-full bg-amber-500/30" />
            <span className="relative flex items-center justify-center w-5 h-5 rounded-full bg-amber-500/20">
              <Loader2 className="h-3 w-3 text-amber-400 animate-spin" />
            </span>
          </div>
        ) : (
          <span className={cn("flex items-center justify-center w-5 h-5 rounded-full", config.bgColor)}>
            {config.icon}
          </span>
        )}
      </div>

      {/* Task Info */}
      <div className="flex-1 min-w-0 text-left">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-medium text-slate-200 group-hover:text-white transition-colors truncate">
            {task.title}
          </h4>
          {task.metadata?.branch && (
            <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400">
              {task.metadata.branch}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-500">
          <span>{task.id}</span>
          {task.metadata?.commit && (
            <>
              <span className="text-slate-600">•</span>
              <span className="font-mono">{task.metadata.commit.slice(0, 7)}</span>
            </>
          )}
        </div>
      </div>

      {/* Duration / Time */}
      <div className="flex-shrink-0 text-right">
        {isRunning && task.startTime ? (
          <div className="flex items-center gap-1.5 text-xs text-amber-400">
            <Timer className="h-3 w-3" />
            {formatDuration(Math.floor((Date.now() - new Date(task.startTime).getTime()) / 1000))}
          </div>
        ) : task.duration ? (
          <div className="text-xs text-slate-400">
            {formatDuration(task.duration)}
          </div>
        ) : null}
        {task.endTime && (
          <div className="text-xs text-slate-500 mt-0.5">
            {formatRelativeTime(task.endTime)}
          </div>
        )}
      </div>

      {/* Arrow */}
      <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-slate-400 transition-colors flex-shrink-0" />
    </button>
  );
}

interface AgentCardProps {
  agent: Agent;
  onTaskClick: (taskId: string) => void;
  isExpanded: boolean;
  onToggle: () => void;
}

function AgentCard({ agent, onTaskClick, isExpanded, onToggle }: AgentCardProps) {
  const status = agentStatusConfig[agent.status];
  
  // Get all tasks for this agent
  const allTasks = useMemo(() => {
    const tasks: Array<{ task: AgentTask; category: ExtendedTaskStatus }> = [];
    if (agent.currentTask) {
      tasks.push({ task: agent.currentTask, category: getTaskCategory(agent.currentTask) });
    }
    agent.taskQueue.forEach(task => tasks.push({ task, category: getTaskCategory(task) }));
    agent.completedTasks.forEach(task => tasks.push({ task, category: getTaskCategory(task) }));
    return tasks;
  }, [agent]);

  // Count tasks by category
  const taskCounts = useMemo(() => {
    const counts: Record<string, number> = {
      merged: 0,
      open: 0,
      pending: 0,
      closed: 0,
      failed: 0,
      running: 0,
    };
    allTasks.forEach(({ category }) => {
      counts[category] = (counts[category] || 0) + 1;
    });
    return counts;
  }, [allTasks]);

  const hasTasks = allTasks.length > 0;

  return (
    <div className={cn(
      "rounded-lg border transition-all duration-200",
      "bg-[#1a1b26] border-white/[0.06]",
      isExpanded && "border-white/[0.12]"
    )}>
      {/* Agent Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02] transition-colors"
      >
        {/* Expand Icon */}
        <ChevronDown className={cn(
          "h-4 w-4 text-slate-500 transition-transform duration-200",
          isExpanded && "rotate-180"
        )} />

        {/* Agent Status Dot */}
        <div className="relative flex-shrink-0">
          <span className={cn("w-2.5 h-2.5 rounded-full", status.color)} />
          {agent.status === 'busy' && (
            <span className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-amber-500 animate-ping opacity-50" />
          )}
        </div>

        {/* Agent Name */}
        <div className="flex-1 text-left">
          <h3 className="text-sm font-medium text-slate-200">{agent.name}</h3>
          <p className="text-xs text-slate-500">{status.label}</p>
        </div>

        {/* Task Counts */}
        <div className="flex items-center gap-1.5">
          {taskCounts.running > 0 && (
            <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-amber-500/10 text-amber-400">
              <Loader2 className="h-3 w-3 animate-spin" />
              {taskCounts.running}
            </span>
          )}
          {taskCounts.pending > 0 && (
            <span className="text-xs px-2 py-1 rounded-full bg-slate-500/10 text-slate-400">
              {taskCounts.pending} pending
            </span>
          )}
          {taskCounts.merged > 0 && (
            <span className="text-xs px-2 py-1 rounded-full bg-violet-500/10 text-violet-400">
              {taskCounts.merged} merged
            </span>
          )}
          {taskCounts.failed > 0 && (
            <span className="text-xs px-2 py-1 rounded-full bg-rose-500/10 text-rose-400">
              {taskCounts.failed} failed
            </span>
          )}
          {taskCounts.closed > 0 && (
            <span className="text-xs px-2 py-1 rounded-full bg-slate-500/10 text-slate-400">
              {taskCounts.closed} closed
            </span>
          )}
          {!hasTasks && (
            <span className="text-xs text-slate-600">No tasks</span>
          )}
        </div>
      </button>

      {/* Expanded Task List */}
      {isExpanded && hasTasks && (
        <div className="border-t border-white/[0.06]">
          {/* Task Categories */}
          {taskCounts.running > 0 && (
            <div className="border-b border-white/[0.04] last:border-b-0">
              <div className="px-4 py-2 bg-amber-500/5 flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 text-amber-400 animate-spin" />
                <span className="text-xs font-medium text-amber-400 uppercase tracking-wider">Running</span>
                <span className="text-xs text-amber-400/60">{taskCounts.running}</span>
              </div>
              {allTasks
                .filter(({ category }) => category === 'running')
                .map(({ task }) => (
                  <TaskRow key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                ))}
            </div>
          )}

          {taskCounts.pending > 0 && (
            <div className="border-b border-white/[0.04] last:border-b-0">
              <div className="px-4 py-2 bg-slate-500/5 flex items-center gap-2">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Pending</span>
                <span className="text-xs text-slate-500">{taskCounts.pending}</span>
              </div>
              {allTasks
                .filter(({ category }) => category === 'pending')
                .map(({ task }) => (
                  <TaskRow key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                ))}
            </div>
          )}

          {taskCounts.merged > 0 && (
            <div className="border-b border-white/[0.04] last:border-b-0">
              <div className="px-4 py-2 bg-violet-500/5 flex items-center gap-2">
                <GitMerge className="h-3.5 w-3.5 text-violet-400" />
                <span className="text-xs font-medium text-violet-400 uppercase tracking-wider">Merged</span>
                <span className="text-xs text-violet-400/60">{taskCounts.merged}</span>
              </div>
              {allTasks
                .filter(({ category }) => category === 'merged')
                .map(({ task }) => (
                  <TaskRow key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                ))}
            </div>
          )}

          {taskCounts.closed > 0 && (
            <div className="border-b border-white/[0.04] last:border-b-0">
              <div className="px-4 py-2 bg-slate-500/5 flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Closed</span>
                <span className="text-xs text-slate-500">{taskCounts.closed}</span>
              </div>
              {allTasks
                .filter(({ category }) => category === 'closed')
                .map(({ task }) => (
                  <TaskRow key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                ))}
            </div>
          )}

          {taskCounts.failed > 0 && (
            <div className="border-b border-white/[0.04] last:border-b-0">
              <div className="px-4 py-2 bg-rose-500/5 flex items-center gap-2">
                <XCircle className="h-3.5 w-3.5 text-rose-400" />
                <span className="text-xs font-medium text-rose-400 uppercase tracking-wider">Failed</span>
                <span className="text-xs text-rose-400/60">{taskCounts.failed}</span>
              </div>
              {allTasks
                .filter(({ category }) => category === 'failed')
                .map(({ task }) => (
                  <TaskRow key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                ))}
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {isExpanded && !hasTasks && (
        <div className="px-4 py-8 text-center border-t border-white/[0.06]">
          <div className="w-12 h-12 rounded-full bg-white/[0.03] flex items-center justify-center mx-auto mb-3">
            <Activity className="h-5 w-5 text-slate-600" />
          </div>
          <p className="text-sm text-slate-500">No tasks assigned to this agent</p>
        </div>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  trend?: string;
}

function StatCard({ label, value, icon, color, trend }: StatCardProps) {
  return (
    <div className="bg-[#1a1b26] border border-white/[0.06] rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-semibold text-slate-200 mt-1">{value}</p>
          {trend && (
            <p className="text-xs text-slate-500 mt-1">{trend}</p>
          )}
        </div>
        <div className={cn("p-2 rounded-lg", color)}>
          {icon}
        </div>
      </div>
    </div>
  );
}

export default function LogPage() {
  const navigate = useNavigate();
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list');
  const [, setSelectedFilter] = useState<string | null>(null);
  
  // Use setSelectedFilter in a click handler to avoid unused variable warning
  const handleFilterClick = () => {
    setSelectedFilter('all');
  };

  // Calculate stats
  const stats = useMemo(() => {
    let totalTasks = 0;
    let running = 0;
    let pending = 0;
    let merged = 0;
    let failed = 0;
    let closed = 0;

    mockAgents.forEach(agent => {
      const tasks = [
        agent.currentTask,
        ...agent.taskQueue,
        ...agent.completedTasks,
      ].filter(Boolean) as AgentTask[];

      tasks.forEach(task => {
        totalTasks++;
        const category = getTaskCategory(task);
        if (category === 'running') running++;
        else if (category === 'pending') pending++;
        else if (category === 'merged') merged++;
        else if (category === 'failed') failed++;
        else if (category === 'closed') closed++;
      });
    });

    return { totalTasks, running, pending, merged, failed, closed };
  }, []);

  const onlineAgents = mockAgents.filter(a => a.status !== 'offline').length;
  const busyAgents = mockAgents.filter(a => a.status === 'busy').length;

  // Filter agents based on search
  const filteredAgents = useMemo(() => {
    return mockAgents.filter(agent => {
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      return (
        agent.name.toLowerCase().includes(query) ||
        agent.currentTask?.title.toLowerCase().includes(query) ||
        agent.taskQueue.some(t => t.title.toLowerCase().includes(query)) ||
        agent.completedTasks.some(t => t.title.toLowerCase().includes(query))
      );
    });
  }, [searchQuery]);

  const toggleAgent = (agentId: string) => {
    setExpandedAgents(prev => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const handleTaskClick = (taskId: string) => {
    navigate(`/task/${taskId}`);
  };

  return (
    <div className="min-h-screen bg-[#0f0f14] text-slate-300">
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 bg-[#0f0f14]/95 backdrop-blur-sm border-b border-white/[0.06]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500">
                <Zap className="h-4 w-4 text-white" />
              </div>
              <span className="text-sm font-semibold text-slate-200">Nexus CI</span>
            </div>

            {/* Navigation */}
            <nav className="hidden md:flex items-center gap-1">
              <button className="px-3 py-1.5 text-sm text-slate-200 bg-white/[0.06] rounded-md">
                Agents
              </button>
              <button className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors">
                Pipelines
              </button>
              <button className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors">
                Builds
              </button>
              <button className="px-3 py-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors">
                Settings
              </button>
            </nav>

            {/* Right Actions */}
            <div className="flex items-center gap-2">
              <button className="p-2 text-slate-500 hover:text-slate-300 transition-colors">
                <RefreshCw className="h-4 w-4" />
              </button>
              <div className="h-4 w-px bg-white/[0.08]" />
              <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-white/[0.04]">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-xs text-slate-400">{onlineAgents} agents</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="border-b border-white/[0.06] bg-[#0f0f14]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Total Tasks"
              value={stats.totalTasks}
              icon={<Activity className="h-4 w-4 text-slate-400" />}
              color="bg-slate-500/10"
            />
            <StatCard
              label="Running"
              value={stats.running}
              icon={<Loader2 className="h-4 w-4 text-amber-400" />}
              color="bg-amber-500/10"
              trend={`${busyAgents} agents busy`}
            />
            <StatCard
              label="Pending"
              value={stats.pending}
              icon={<Clock className="h-4 w-4 text-slate-400" />}
              color="bg-slate-500/10"
            />
            <StatCard
              label="Merged"
              value={stats.merged}
              icon={<GitMerge className="h-4 w-4 text-violet-400" />}
              color="bg-violet-500/10"
            />
            <StatCard
              label="Closed"
              value={stats.closed}
              icon={<CheckCircle2 className="h-4 w-4 text-slate-400" />}
              color="bg-slate-500/10"
            />
            <StatCard
              label="Failed"
              value={stats.failed}
              icon={<XCircle className="h-4 w-4 text-rose-400" />}
              color="bg-rose-500/10"
            />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Toolbar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-slate-200">Agents</h1>
            <span className="text-xs px-2 py-0.5 rounded-full bg-white/[0.06] text-slate-500">
              {filteredAgents.length}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <input
                type="text"
                placeholder="Search agents or tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full sm:w-64 pl-9 pr-4 py-2 text-sm bg-[#1a1b26] border border-white/[0.08] rounded-lg text-slate-300 placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all"
              />
            </div>

            {/* Filter */}
            <button 
              onClick={handleFilterClick}
              className="flex items-center gap-2 px-3 py-2 text-sm text-slate-400 bg-[#1a1b26] border border-white/[0.08] rounded-lg hover:border-white/[0.12] transition-colors"
            >
              <Filter className="h-4 w-4" />
              <span className="hidden sm:inline">Filter</span>
            </button>

            {/* View Toggle */}
            <div className="flex items-center bg-[#1a1b26] border border-white/[0.08] rounded-lg p-1">
              <button
                onClick={() => setViewMode('list')}
                className={cn(
                  "p-1.5 rounded transition-colors",
                  viewMode === 'list' ? "bg-white/[0.08] text-slate-200" : "text-slate-500 hover:text-slate-300"
                )}
              >
                <List className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={cn(
                  "p-1.5 rounded transition-colors",
                  viewMode === 'grid' ? "bg-white/[0.08] text-slate-200" : "text-slate-500 hover:text-slate-300"
                )}
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Agent List */}
        <div className={cn(
          "space-y-3",
          viewMode === 'grid' && "grid grid-cols-1 lg:grid-cols-2 gap-3"
        )}>
          {filteredAgents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onTaskClick={handleTaskClick}
              isExpanded={expandedAgents.has(agent.id)}
              onToggle={() => toggleAgent(agent.id)}
            />
          ))}
        </div>

        {/* Empty State */}
        {filteredAgents.length === 0 && (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-full bg-white/[0.03] flex items-center justify-center mx-auto mb-4">
              <Search className="h-8 w-8 text-slate-600" />
            </div>
            <h3 className="text-sm font-medium text-slate-400 mb-1">No agents found</h3>
            <p className="text-xs text-slate-600">Try adjusting your search query</p>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-white/[0.06] mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between text-xs text-slate-600">
            <div className="flex items-center gap-4">
              <span>Nexus CI v0.1.0</span>
              <span>•</span>
              <span>{mockAgents.length} agents</span>
              <span>•</span>
              <span>{stats.totalTasks} total tasks</span>
            </div>
            <div className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              <span>Updated {formatRelativeTime(new Date().toISOString())}</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
