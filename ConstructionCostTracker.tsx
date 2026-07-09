import { useState, useMemo, useRef } from "react";
import Papa from "papaparse";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line,
} from "recharts";
import {
  Card, CardContent, CardHeader, CardTitle,
  Button, Input, Label,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Badge,
} from "shadcn";
import {
  ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent,
} from "shadcn";
import {
  HardHat, Package, Boxes, Wallet, TrendingUp, Trash2, Plus, Download,
  AlertTriangle, Building2, Calendar, CheckCircle2, Upload, Paperclip,
  X, FileText, Info,
} from "lucide-react";
import { triggerUserFileDownload } from "@dust/react-hooks";

type Category = "Labour" | "Material" | "Misc";

type Expense = {
  id: string;
  date: string;
  category: Category;
  phase: string;
  description: string;
  amount: number;
  receiptUrl?: string;
  receiptName?: string;
};

const CATEGORIES: Category[] = ["Labour", "Material", "Misc"];

const PHASES = [
  "Foundation",
  "Structure",
  "Masonry",
  "Roofing",
  "Plumbing & Electrical",
  "Finishing",
  "Interior",
  "Exterior",
  "General",
  "Other",
];

const CATEGORY_COLOR: Record<Category, string> = {
  Labour: "var(--chart-1)",
  Material: "var(--chart-2)",
  Misc: "var(--chart-3)",
};

const CATEGORY_BADGE: Record<Category, string> = {
  Labour: "bg-emerald-100 text-emerald-700 border-emerald-200",
  Material: "bg-sky-100 text-sky-700 border-sky-200",
  Misc: "bg-violet-100 text-violet-700 border-violet-200",
};

const SEED_EXPENSES: Expense[] = [
  { id: "e1", date: "2026-01-15", category: "Material", phase: "Foundation", description: "Cement (OPC 53 grade) - 200 bags", amount: 110000 },
  { id: "e2", date: "2026-01-18", category: "Labour", phase: "Foundation", description: "Excavation & foundation labour", amount: 65000 },
  { id: "e3", date: "2026-01-25", category: "Material", phase: "Foundation", description: "Steel reinforcement bars (TMT)", amount: 185000 },
  { id: "e4", date: "2026-02-05", category: "Labour", phase: "Structure", description: "Mason & helper wages - RCC work", amount: 92000 },
  { id: "e5", date: "2026-02-12", category: "Material", phase: "Structure", description: "Ready-mix concrete", amount: 145000 },
  { id: "e6", date: "2026-02-28", category: "Misc", phase: "Structure", description: "Equipment rental (mixer, vibrator)", amount: 22000 },
  { id: "e7", date: "2026-03-10", category: "Labour", phase: "Masonry", description: "Brickwork labour charges", amount: 78000 },
  { id: "e8", date: "2026-03-15", category: "Material", phase: "Masonry", description: "Bricks (12,000 nos)", amount: 96000 },
  { id: "e9", date: "2026-03-20", category: "Misc", phase: "General", description: "Municipal permits & approvals", amount: 35000 },
  { id: "e10", date: "2026-04-05", category: "Labour", phase: "Roofing", description: "Roofing/slab labour", amount: 54000 },
  { id: "e11", date: "2026-04-12", category: "Material", phase: "Roofing", description: "Waterproofing materials", amount: 42000 },
  { id: "e12", date: "2026-04-25", category: "Labour", phase: "Plumbing & Electrical", description: "Plumber & electrician wages", amount: 68000 },
  { id: "e13", date: "2026-05-02", category: "Material", phase: "Plumbing & Electrical", description: "Pipes, wires & fittings", amount: 118000 },
  { id: "e14", date: "2026-05-18", category: "Material", phase: "Finishing", description: "Tiles & flooring material", amount: 165000 },
  { id: "e15", date: "2026-05-28", category: "Labour", phase: "Finishing", description: "Tiling & plastering labour", amount: 88000 },
  { id: "e16", date: "2026-06-08", category: "Material", phase: "Finishing", description: "Paint & putty", amount: 58000 },
  { id: "e17", date: "2026-06-15", category: "Misc", phase: "General", description: "Site transportation & logistics", amount: 28000 },
  { id: "e18", date: "2026-06-25", category: "Labour", phase: "Interior", description: "Carpentry - doors & windows", amount: 95000 },
  { id: "e19", date: "2026-07-02", category: "Material", phase: "Interior", description: "Wood & hardware fittings", amount: 132000 },
  { id: "e20", date: "2026-07-05", category: "Misc", phase: "General", description: "Contingency / miscellaneous", amount: 15000 },
];

const CURRENCIES = ["₹", "$", "€", "£"];
const CSV_TEMPLATE = "Date,Category,Phase,Description,Amount\n2026-01-15,Material,Foundation,Cement - 50 bags,27500\n2026-01-18,Labour,Foundation,Excavation labour,15000\n2026-01-20,Misc,General,Site permit fee,5000\n";

function formatMoney(value: number, symbol: string) {
  return `${symbol}${Math.round(value).toLocaleString("en-IN")}`;
}

function monthLabel(dateStr: string) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function normalizeCategory(raw: string): Category | null {
  const v = raw.trim().toLowerCase();
  if (v.startsWith("labo")) return "Labour";
  if (v.startsWith("mat")) return "Material";
  if (v.startsWith("misc") || v.startsWith("other")) return "Misc";
  return null;
}

function isImageFile(name: string) {
  return /\.(png|jpe?g|gif|webp|heic)$/i.test(name);
}

const chartConfig: ChartConfig = {
  Labour: { label: "Labour", color: "var(--chart-1)" },
  Material: { label: "Material", color: "var(--chart-2)" },
  Misc: { label: "Misc", color: "var(--chart-3)" },
};

type ImportSummary = {
  imported: number;
  skipped: number;
  reasons: string[];
};

export default function ConstructionCostTracker() {
  const [currency, setCurrency] = useState<string>("₹");
  const [expenses, setExpenses] = useState<Expense[]>(SEED_EXPENSES);
  const [categoryBudgets, setCategoryBudgets] = useState<Record<Category, number>>({
    Labour: 900000,
    Material: 1400000,
    Misc: 250000,
  });
  const [filterCategory, setFilterCategory] = useState<"All" | Category>("All");
  const [confirmClear, setConfirmClear] = useState(false);
  const [importSummary, setImportSummary] = useState<ImportSummary | null>(null);
  const [importError, setImportError] = useState<string>("");

  const [formDate, setFormDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [formCategory, setFormCategory] = useState<Category>("Material");
  const [formPhase, setFormPhase] = useState<string>(PHASES[0]);
  const [formDescription, setFormDescription] = useState<string>("");
  const [formAmount, setFormAmount] = useState<string>("");
  const [formReceipt, setFormReceipt] = useState<File | null>(null);
  const [formError, setFormError] = useState<string>("");

  const csvInputRef = useRef<HTMLInputElement>(null);
  const formReceiptInputRef = useRef<HTMLInputElement>(null);
  const rowReceiptInputRef = useRef<HTMLInputElement>(null);
  const [pendingReceiptRowId, setPendingReceiptRowId] = useState<string | null>(null);

  const totals = useMemo(() => {
    const byCategory: Record<Category, number> = { Labour: 0, Material: 0, Misc: 0 };
    let total = 0;
    for (const e of expenses) {
      byCategory[e.category] += e.amount;
      total += e.amount;
    }
    return { byCategory, total };
  }, [expenses]);

  const totalBudget = categoryBudgets.Labour + categoryBudgets.Material + categoryBudgets.Misc;
  const remaining = totalBudget - totals.total;
  const percentUsed = totalBudget > 0 ? (totals.total / totalBudget) * 100 : 0;
  const billsAttached = expenses.filter((e) => e.receiptUrl).length;

  const pieData = useMemo(
    () =>
      CATEGORIES.map((c) => ({
        name: c,
        value: totals.byCategory[c],
      })).filter((d) => d.value > 0),
    [totals]
  );

  const phaseData = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of expenses) {
      map.set(e.phase, (map.get(e.phase) ?? 0) + e.amount);
    }
    return Array.from(map.entries())
      .map(([phase, amount]) => ({ phase, amount }))
      .sort((a, b) => b.amount - a.amount);
  }, [expenses]);

  const monthlyData = useMemo(() => {
    const map = new Map<string, { month: string; Labour: number; Material: number; Misc: number; sortKey: string }>();
    const sorted = [...expenses].sort((a, b) => a.date.localeCompare(b.date));
    for (const e of sorted) {
      const key = e.date.slice(0, 7);
      const label = monthLabel(e.date);
      if (!map.has(key)) {
        map.set(key, { month: label, Labour: 0, Material: 0, Misc: 0, sortKey: key });
      }
      const entry = map.get(key)!;
      entry[e.category] += e.amount;
    }
    return Array.from(map.values()).sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  }, [expenses]);

  const sortedExpenses = useMemo(() => {
    const filtered = filterCategory === "All" ? expenses : expenses.filter((e) => e.category === filterCategory);
    return [...filtered].sort((a, b) => b.date.localeCompare(a.date));
  }, [expenses, filterCategory]);

  function handleAddExpense() {
    const amountNum = parseFloat(formAmount);
    if (!formDescription.trim()) {
      setFormError("Please add a description.");
      return;
    }
    if (isNaN(amountNum) || amountNum <= 0) {
      setFormError("Please enter a valid amount greater than 0.");
      return;
    }
    if (!formDate) {
      setFormError("Please pick a date.");
      return;
    }
    const receiptUrl = formReceipt ? URL.createObjectURL(formReceipt) : undefined;
    const newExpense: Expense = {
      id: `e${Date.now()}`,
      date: formDate,
      category: formCategory,
      phase: formPhase,
      description: formDescription.trim(),
      amount: amountNum,
      receiptUrl,
      receiptName: formReceipt?.name,
    };
    setExpenses((prev) => [newExpense, ...prev]);
    setFormDescription("");
    setFormAmount("");
    setFormReceipt(null);
    setFormError("");
  }

  function handleDelete(id: string) {
    setExpenses((prev) => {
      const target = prev.find((e) => e.id === id);
      if (target?.receiptUrl) URL.revokeObjectURL(target.receiptUrl);
      return prev.filter((e) => e.id !== id);
    });
  }

  function handleClearAll() {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    expenses.forEach((e) => {
      if (e.receiptUrl) URL.revokeObjectURL(e.receiptUrl);
    });
    setExpenses([]);
    setConfirmClear(false);
    setImportSummary(null);
  }

  function handleDownloadCsv() {
    const header = "Date,Category,Phase,Description,Amount\n";
    const rows = expenses
      .slice()
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((e) => `${e.date},${e.category},${e.phase},"${e.description.replace(/"/g, '""')}",${e.amount}`)
      .join("\n");
    triggerUserFileDownload({
      content: header + rows,
      filename: "construction_cost_tracker.csv",
    });
  }

  function handleDownloadTemplate() {
    triggerUserFileDownload({
      content: CSV_TEMPLATE,
      filename: "expense_import_template.csv",
    });
  }

  function updateCategoryBudget(cat: Category, value: string) {
    const num = parseFloat(value);
    setCategoryBudgets((prev) => ({ ...prev, [cat]: isNaN(num) ? 0 : num }));
  }

  function handleCsvFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportError("");
    setImportSummary(null);

    file
      .text()
      .then((text) => {
        const parsed = Papa.parse<Record<string, string>>(text, {
          header: true,
          skipEmptyLines: "greedy",
        });

        if (parsed.errors.length > 0 && parsed.data.length === 0) {
          setImportError(`Could not parse CSV: ${parsed.errors[0].message}`);
          return;
        }

        const reasons: string[] = [];
        const newExpenses: Expense[] = [];

        parsed.data.forEach((row, idx) => {
          const rowNum = idx + 2;
          const rawDate = row.Date ?? row.date ?? "";
          const rawCategory = row.Category ?? row.category ?? "";
          const rawPhase = row.Phase ?? row.phase ?? "General";
          const rawDescription = row.Description ?? row.description ?? "";
          const rawAmount = row.Amount ?? row.amount ?? "";

          if (!rawDate || !rawCategory || !rawDescription || !rawAmount) {
            reasons.push(`Row ${rowNum}: missing required field(s), skipped.`);
            return;
          }

          const category = normalizeCategory(rawCategory);
          if (!category) {
            reasons.push(`Row ${rowNum}: unrecognized category "${rawCategory}", skipped.`);
            return;
          }

          const amountNum = parseFloat(String(rawAmount).replace(/[,₹$€£\s]/g, ""));
          if (isNaN(amountNum) || amountNum <= 0) {
            reasons.push(`Row ${rowNum}: invalid amount "${rawAmount}", skipped.`);
            return;
          }

          const dateVal = new Date(rawDate);
          const dateStr = isNaN(dateVal.getTime()) ? rawDate : dateVal.toISOString().slice(0, 10);

          newExpenses.push({
            id: `e${Date.now()}_${idx}`,
            date: dateStr,
            category,
            phase: rawPhase.trim() || "General",
            description: rawDescription.trim(),
            amount: amountNum,
          });
        });

        if (newExpenses.length > 0) {
          setExpenses((prev) => [...newExpenses, ...prev]);
        }
        setImportSummary({ imported: newExpenses.length, skipped: reasons.length, reasons: reasons.slice(0, 8) });
      })
      .catch(() => setImportError("Could not read the selected file."));

    e.target.value = "";
  }

  function handleFormReceiptChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    setFormReceipt(file ?? null);
    e.target.value = "";
  }

  function handleRowReceiptClick(id: string) {
    setPendingReceiptRowId(id);
    rowReceiptInputRef.current?.click();
  }

  function handleRowReceiptChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && pendingReceiptRowId) {
      const url = URL.createObjectURL(file);
      setExpenses((prev) =>
        prev.map((exp) =>
          exp.id === pendingReceiptRowId ? { ...exp, receiptUrl: url, receiptName: file.name } : exp
        )
      );
    }
    setPendingReceiptRowId(null);
    e.target.value = "";
  }

  function handleRemoveReceipt(id: string) {
    setExpenses((prev) =>
      prev.map((exp) => {
        if (exp.id !== id) return exp;
        if (exp.receiptUrl) URL.revokeObjectURL(exp.receiptUrl);
        return { ...exp, receiptUrl: undefined, receiptName: undefined };
      })
    );
  }

  const budgetStatusColor = percentUsed >= 100 ? "text-red-600" : percentUsed >= 85 ? "text-amber-600" : "text-emerald-600";

  return (
    <main className="min-h-screen bg-background px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-indigo-600 p-2">
              <Building2 className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-semibold text-indigo-700">Construction Cost Tracker</h1>
              <p className="text-sm text-muted-foreground">Track labour, material & misc spending against budget</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Label className="text-sm text-muted-foreground">Currency</Label>
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger className="w-20">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CURRENCIES.map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </header>

        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Wallet className="h-4 w-4 text-indigo-600" />
                Total Budget
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">{formatMoney(totalBudget, currency)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <TrendingUp className="h-4 w-4 text-indigo-600" />
                Total Spent
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">{formatMoney(totals.total, currency)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                {remaining < 0 ? (
                  <AlertTriangle className="h-4 w-4 text-red-600" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                )}
                Remaining
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className={`text-2xl font-semibold ${remaining < 0 ? "text-red-600" : "text-foreground"}`}>
                {formatMoney(remaining, currency)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Paperclip className="h-4 w-4 text-indigo-600" />
                Bills Attached
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {billsAttached} <span className="text-base text-muted-foreground">/ {expenses.length}</span>
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Calendar className="h-4 w-4 text-indigo-600" />
              Budget Used
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-2xl font-semibold ${budgetStatusColor}`}>{percentUsed.toFixed(1)}%</p>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={`h-full ${percentUsed >= 100 ? "bg-red-500" : percentUsed >= 85 ? "bg-amber-500" : "bg-emerald-500"}`}
                style={{ width: `${Math.min(percentUsed, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Budget by Category</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {CATEGORIES.map((cat) => {
              const spent = totals.byCategory[cat];
              const budget = categoryBudgets[cat];
              const pct = budget > 0 ? (spent / budget) * 100 : 0;
              const Icon = cat === "Labour" ? HardHat : cat === "Material" ? Package : Boxes;
              return (
                <div key={cat} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 font-medium text-foreground">
                      <Icon className="h-4 w-4" style={{ color: CATEGORY_COLOR[cat] }} />
                      {cat}
                    </span>
                    <span className="text-muted-foreground">
                      {formatMoney(spent, currency)} / {formatMoney(budget, currency)}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                      className={`h-full ${pct >= 100 ? "bg-red-500" : pct >= 85 ? "bg-amber-500" : "bg-emerald-500"}`}
                      style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: pct < 85 ? CATEGORY_COLOR[cat] : undefined }}
                    />
                  </div>
                  <div className="flex items-center gap-2 pt-1">
                    <Label className="text-xs text-muted-foreground">Set budget:</Label>
                    <Input
                      type="number"
                      value={budget}
                      onChange={(e) => updateCategoryBudget(cat, e.target.value)}
                      className="h-8 w-32 text-sm"
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
          <Card>
            <CardHeader>
              <CardTitle>Spend by Category</CardTitle>
            </CardHeader>
            <CardContent>
              {pieData.length === 0 ? (
                <p className="text-sm text-muted-foreground">No data available.</p>
              ) : (
                <ChartContainer config={chartConfig} className="h-72 w-full">
                  <PieChart>
                    <ChartTooltip
                      content={<ChartTooltipContent />}
                      formatter={(value: number, name: string) => [formatMoney(value, currency), name]}
                    />
                    <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={CATEGORY_COLOR[entry.name as Category]} />
                      ))}
                    </Pie>
                  </PieChart>
                </ChartContainer>
              )}
              <div className="mt-3 flex flex-wrap justify-center gap-3">
                {CATEGORIES.map((c) => (
                  <span key={c} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CATEGORY_COLOR[c] }} />
                    {c}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Spend by Phase</CardTitle>
            </CardHeader>
            <CardContent>
              {phaseData.length === 0 ? (
                <p className="text-sm text-muted-foreground">No data available.</p>
              ) : (
                <ChartContainer config={chartConfig} className="h-72 w-full">
                  <BarChart data={phaseData} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(v) => formatMoney(v, currency)} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="phase" width={110} tick={{ fontSize: 11 }} />
                    <ChartTooltip
                      content={<ChartTooltipContent />}
                      formatter={(value: number) => [formatMoney(value, currency), "Spend"]}
                    />
                    <Bar dataKey="amount" radius={4}>
                      {phaseData.map((entry, idx) => (
                        <Cell key={entry.phase} fill={`var(--chart-${(idx % 5) + 1})`} />
                      ))}
                    </Bar>
                  </BarChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Monthly Spend Trend</CardTitle>
          </CardHeader>
          <CardContent>
            {monthlyData.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data available.</p>
            ) : (
              <ChartContainer config={chartConfig} className="h-72 w-full">
                <LineChart data={monthlyData} margin={{ top: 20, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => formatMoney(v, currency)} tick={{ fontSize: 11 }} />
                  <ChartTooltip
                    content={<ChartTooltipContent />}
                    formatter={(value: number, name: string) => [formatMoney(value, currency), name]}
                  />
                  <Line type="monotone" dataKey="Labour" stroke="var(--color-Labour)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="Material" stroke="var(--color-Material)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="Misc" stroke="var(--color-Misc)" strokeWidth={2} dot={false} />
                </LineChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Import Expenses from CSV</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Upload a CSV with columns <span className="font-mono text-xs">Date, Category, Phase, Description, Amount</span>.
              Category should be Labour, Material, or Misc.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => csvInputRef.current?.click()} className="bg-indigo-600 text-white hover:bg-indigo-700">
                <Upload className="mr-1.5 h-4 w-4" />
                Import CSV
              </Button>
              <Button variant="outline" onClick={handleDownloadTemplate}>
                <Download className="mr-1.5 h-4 w-4" />
                Download template
              </Button>
              <input
                ref={csvInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={handleCsvFileChange}
              />
            </div>
            {importError && (
              <p className="flex items-center gap-2 text-sm text-red-600">
                <AlertTriangle className="h-4 w-4" />
                {importError}
              </p>
            )}
            {importSummary && (
              <div className="rounded-lg border bg-card p-3 text-sm">
                <p className="flex items-center gap-2 font-medium text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  Imported {importSummary.imported} row{importSummary.imported === 1 ? "" : "s"}
                  {importSummary.skipped > 0 ? `, skipped ${importSummary.skipped}` : ""}.
                </p>
                {importSummary.reasons.length > 0 && (
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                    {importSummary.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Add Expense</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Date</Label>
                <Input type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Category</Label>
                <Select value={formCategory} onValueChange={(v) => setFormCategory(v as Category)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Phase</Label>
                <Select value={formPhase} onValueChange={setFormPhase}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PHASES.map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Amount</Label>
                <Input
                  type="number"
                  placeholder="0"
                  value={formAmount}
                  onChange={(e) => setFormAmount(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Description</Label>
              <Input
                placeholder="e.g. Cement - 50 bags"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Bill / invoice (optional)</Label>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => formReceiptInputRef.current?.click()}>
                  <Paperclip className="mr-1.5 h-4 w-4" />
                  {formReceipt ? "Change file" : "Attach file"}
                </Button>
                {formReceipt && (
                  <span className="flex items-center gap-1 text-sm text-muted-foreground">
                    <FileText className="h-4 w-4" />
                    {formReceipt.name}
                    <button
                      type="button"
                      onClick={() => setFormReceipt(null)}
                      aria-label="Remove attached file"
                      className="ml-1 text-muted-foreground hover:text-red-600"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                )}
                <input
                  ref={formReceiptInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  className="hidden"
                  onChange={handleFormReceiptChange}
                />
              </div>
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <Button onClick={handleAddExpense} className="bg-indigo-600 text-white hover:bg-indigo-700">
              <Plus className="mr-1.5 h-4 w-4" />
              Add Expense
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Expense Log ({sortedExpenses.length})</CardTitle>
            <div className="flex items-center gap-2">
              <Select value={filterCategory} onValueChange={(v) => setFilterCategory(v as "All" | Category)}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="All">All</SelectItem>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={handleDownloadCsv}>
                <Download className="mr-1.5 h-4 w-4" />
                CSV
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <input
              ref={rowReceiptInputRef}
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={handleRowReceiptChange}
            />
            {sortedExpenses.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data available.</p>
            ) : (
              <div className="space-y-2">
                {sortedExpenses.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge className={`border ${CATEGORY_BADGE[e.category]}`}>{e.category}</Badge>
                        <span className="text-xs text-muted-foreground">{e.phase}</span>
                      </div>
                      <p className="mt-1 truncate text-sm font-medium text-foreground">{e.description}</p>
                      <p className="text-xs text-muted-foreground">{e.date}</p>
                      {e.receiptUrl ? (
                        <div className="mt-1.5 flex items-center gap-2">
                          <a
                            href={e.receiptUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
                          >
                            {isImageFile(e.receiptName ?? "") ? <FileText className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                            View {e.receiptName ?? "receipt"}
                          </a>
                          <button
                            type="button"
                            onClick={() => handleRemoveReceipt(e.id)}
                            aria-label="Remove bill"
                            className="text-muted-foreground hover:text-red-600"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleRowReceiptClick(e.id)}
                          className="mt-1.5 flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
                        >
                          <Paperclip className="h-3.5 w-3.5" />
                          Attach bill / invoice
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="whitespace-nowrap font-semibold text-foreground">
                        {formatMoney(e.amount, currency)}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => handleDelete(e.id)}
                        aria-label="Delete expense"
                      >
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Info className="h-3.5 w-3.5" />
                Attached bills are stored for this session only and are not saved after the frame reloads.
              </p>
              <Button variant={confirmClear ? "destructive" : "outline"} onClick={handleClearAll}>
                {confirmClear ? "Confirm clear all data" : "Clear all data"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
