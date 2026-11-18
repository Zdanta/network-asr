import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Card, Input, LoadingSkeleton, useToast } from "../../components/ui";
import { api } from "../../lib/api-client";
import { queryClient } from "../../lib/query-client";

type Policy = { enabled: boolean; points: number; ip_points: number; global_points: number; ip_claims: number; upload_mb: number; session_days: number };
type Guests = { total: number; converted: number; startedTasks: number; successfulTasks: number; payingVisitors: number;
  reservedAndUsed24h: number; hasMore: boolean; records: Array<{ userId: number; state: string; remainingPoints: number; initialPoints: number; network: string; createdAt: string }> };
const fields: Array<[keyof Omit<Policy, "enabled">, string]> = [["points", "新访客赠送积分"], ["ip_points", "同一领取网络24小时积分上限"],
  ["global_points", "全站访客24小时积分上限"], ["ip_claims", "同一网络24小时领取设备数"], ["upload_mb", "访客单个文件上限（MB）"], ["session_days", "访客身份有效天数"]];
function PolicyForm({ policy }: { policy: Policy }) {
  const [value, setValue] = useState(policy);
  const { showToast } = useToast();
  const save = useMutation({ mutationFn: () => api.put<Policy>("/admin/guest-policy", value), onSuccess: async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ["admin", "guest-policy"] }), queryClient.invalidateQueries({ queryKey: ["public", "experience"] })]);
    showToast({ tone: "success", title: "体验设置已保存" });
  }, onError: (error) => showToast({ tone: "error", title: "保存失败", description: error.message }) });
  function submit(event: FormEvent) { event.preventDefault(); save.mutate(); }
  return <form className="admin-form" onSubmit={submit}><label><input type="checkbox" checked={value.enabled} onChange={(event) => setValue({ ...value, enabled: event.target.checked })} /> 开放免注册体验</label>
    <p className="muted-text">修改赠送点数只影响新领取，不重写已有余额。网络与全站上限包含已消耗及处理中预留积分。</p>
    {fields.map(([key, label]) => <Input key={key} label={label} type="number" min="1" required value={value[key]}
      onChange={(event) => setValue({ ...value, [key]: Number(event.target.value) })} />)}<Button type="submit" loading={save.isPending}>保存设置</Button></form>;
}
export function AdminGuestsPage() {
  const [page, setPage] = useState(1);
  const policy = useQuery({ queryKey: ["admin", "guest-policy"], queryFn: () => api.get<Policy>("/admin/guest-policy") });
  const guests = useQuery({ queryKey: ["admin", "guests", page], queryFn: () => api.get<Guests>(`/admin/guests?pageNo=${page}&pageSize=20`), placeholderData: (old) => old });
  const data = guests.data;
  const stateName: Record<string, string> = { GUEST: "体验中", FORMAL: "已注册", MERGED: "已归入原账号", EXPIRED: "已过期" };
  return <div className="page-stack admin-page"><div className="page-heading admin-heading"><div><p className="eyebrow">体验管理</p><h1>访客体验</h1></div>
    <Button variant="ghost" loading={guests.isFetching} onClick={() => void guests.refetch()}>刷新</Button></div>
    <div className="admin-metric-grid">{[["领取设备", data?.total], ["提交 / 成功任务", `${data?.startedTasks ?? 0} / ${data?.successfulTasks ?? 0}`],
      ["注册 / 购买访客", `${data?.converted ?? 0} / ${data?.payingVisitors ?? 0}`], ["24小时预留与消耗", data?.reservedAndUsed24h]].map(([name, count]) =>
      <Card key={String(name)}><p>{name}</p><h2>{count ?? "-"}</h2></Card>)}</div>
    {guests.isError || policy.isError ? <p className="error-text">体验数据读取失败，请刷新重试。</p> : null}
    <section className="admin-workbench-grid"><Card className="admin-table-card" title="体验记录">
      {data ? <><div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>访客编号</th><th>状态</th><th>赠送 / 剩余</th><th>领取网络标识</th><th>创建时间</th></tr></thead>
        <tbody>{data.records.map((row) => <tr key={row.userId}><td>{row.userId}</td><td>{stateName[row.state] ?? row.state}</td><td>{row.initialPoints} / {row.remainingPoints}</td><td>{row.network}</td><td>{new Date(row.createdAt).toLocaleString("zh-CN")}</td></tr>)}</tbody></table></div>
        <div className="admin-row-actions"><Button size="sm" disabled={guests.isFetching || page <= 1} onClick={() => setPage(page - 1)}>上一页</Button><span>第 {page} 页</span><Button size="sm" disabled={guests.isFetching || !data.hasMore} onClick={() => setPage(page + 1)}>下一页</Button></div></> : <LoadingSkeleton lines={4} />}
    </Card><Card title="体验设置">{policy.data ? <PolicyForm key={JSON.stringify(policy.data)} policy={policy.data} /> : <LoadingSkeleton lines={4} />}</Card></section></div>;
}
