/**
 * MemOmicsPanel — right sidebar panel showing context stats, usage rates,
 * analysis results directory, and session information.
 */
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card } from "@nous-research/ui/ui/components/card";
import { cn } from "@/lib/utils";
import {
  Activity,
  BarChart3,
  Cpu,
  Database,
  FolderOpen,
  MessageSquare,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";

interface MemOmicsPanelProps {
  className?: string;
}

interface StatsState {
  contextTokensUsed: number;
  contextTokensMax: number;
  apiCallsToday: number;
  sessionsActive: number;
  resultsDir: string;
  resultsFiles: string[];
}

export function MemOmicsPanel({ className }: MemOmicsPanelProps) {
  const [stats, setStats] = useState<StatsState>({
    contextTokensUsed: 0,
    contextTokensMax: 128000,
    apiCallsToday: 0,
    sessionsActive: 1,
    resultsDir: "E:/MemOmics-Agent/hermes-agent/results",
    resultsFiles: [],
  });

  // Poll results directory
  useEffect(() => {
    const fetchResults = async () => {
      try {
        const resp = await fetch("/api/results/list");
        if (resp.ok) {
          const data = await resp.json();
          setStats((s) => ({
            ...s,
            resultsDir: data.dir || s.resultsDir,
            resultsFiles: data.files || [],
          }));
        }
      } catch {
        // Fallback: show static info
      }
    };
    fetchResults();
    const interval = setInterval(fetchResults, 30000);
    return () => clearInterval(interval);
  }, []);

  const usagePercent =
    stats.contextTokensMax > 0
      ? Math.round((stats.contextTokensUsed / stats.contextTokensMax) * 100)
      : 0;

  const usageColor =
    usagePercent > 80 ? "bg-red-500" : usagePercent > 50 ? "bg-amber-500" : "bg-emerald-500";

  return (
    <div className={cn("flex flex-col gap-4 p-3", className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <Activity className="h-4 w-4 text-emerald-600" />
        <span className="text-sm font-semibold text-midground">MemOmics</span>
        <Badge tone="success" className="ml-auto text-[10px]">
          v1.0
        </Badge>
      </div>

      {/* Context Window Usage */}
      <Card className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <BarChart3 className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Context Window</span>
        </div>
        <div className="flex items-end gap-2 mb-1">
          <span className="text-lg font-bold">{stats.contextTokensUsed.toLocaleString()}</span>
          <span className="text-xs text-muted-foreground">
            / {stats.contextTokensMax.toLocaleString()} tokens
          </span>
        </div>
        <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", usageColor)}
            style={{ width: `${Math.min(usagePercent, 100)}%` }}
          />
        </div>
        <span className="text-[10px] text-muted-foreground mt-1 block">
          {usagePercent}% used
        </span>
      </Card>

      {/* Usage Stats */}
      <Card className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Usage Rate</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col">
            <span className="text-lg font-bold">{stats.apiCallsToday}</span>
            <span className="text-[10px] text-muted-foreground">API calls today</span>
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-bold">{stats.sessionsActive}</span>
            <span className="text-[10px] text-muted-foreground">Active sessions</span>
          </div>
        </div>
      </Card>

      {/* System Info */}
      <Card className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">System</span>
        </div>
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Model</span>
            <span className="font-medium">deepseek-v4-pro</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Provider</span>
            <span className="font-medium">DCS Cloud</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Gateway</span>
            <Badge tone="success" className="text-[10px] h-4">
              live
            </Badge>
          </div>
        </div>
      </Card>

      {/* Analysis Results */}
      <Card className="p-3 flex-1 min-h-0 overflow-auto">
        <div className="flex items-center gap-2 mb-2">
          <FolderOpen className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Results</span>
        </div>
        {stats.resultsFiles.length > 0 ? (
          <div className="space-y-1">
            {stats.resultsFiles.slice(0, 10).map((f, i) => (
              <div key={i} className="text-[11px] text-muted-foreground truncate hover:text-foreground cursor-pointer">
                📄 {f}
              </div>
            ))}
            {stats.resultsFiles.length > 10 && (
              <div className="text-[10px] text-muted-foreground">
                ... and {stats.resultsFiles.length - 10} more files
              </div>
            )}
          </div>
        ) : (
          <div className="text-[11px] text-muted-foreground text-center py-4">
            <Database className="h-5 w-5 mx-auto mb-1 opacity-30" />
            No results yet.
            <br />
            <span className="text-[10px]">Start an analysis to see results here.</span>
          </div>
        )}
      </Card>

      {/* Quick Actions */}
      <Card className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Quick Actions</span>
        </div>
        <div className="space-y-1.5">
          <Button
            ghost
            size="sm"
            className="w-full justify-start text-xs h-7"
          >
            💬 New Analysis
          </Button>
          <Button
            ghost
            size="sm"
            className="w-full justify-start text-xs h-7"
          >
            ⚙️ Models
          </Button>
        </div>
      </Card>
    </div>
  );
}
