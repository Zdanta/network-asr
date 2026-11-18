import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, FileAudio2, Link2, UploadCloud } from "lucide-react";

import { Badge, Button, Card, EmptyState, Input, LoadingSkeleton, useToast } from "../components/ui";
import { queryClient } from "../lib/query-client";
import { patchTaskCache, upsertTaskCache } from "../lib/task-cache";
import { createImportJob, getImportJob, uploadFile } from "../services/files";
import { createTask } from "../services/tasks";
import type { ImportJobStatus, TaskListItem } from "../types/api";
import { ensureExperience, getExperience } from "../services/guest";
import { useAuthStore } from "../store/auth-store";
import { readUploadDraft, saveUploadDraft, clearUploadDraft } from "../lib/upload-draft";

type LocalUploadResult = {
  fileNo: string;
  taskNo: string;
  sourceFileName: string;
};

function isTerminalStatus(status?: string) {
  return status === "SUCCESS" || status === "FAIL";
}

function taskFromLocalResult(result: LocalUploadResult): TaskListItem {
  return {
    taskNo: result.taskNo,
    fileNo: result.fileNo,
    sourceFileName: result.sourceFileName,
    status: "INIT",
    stage: "等待处理",
    progress: 0,
    createdAt: new Date().toISOString(),
  };
}

function taskFromImportJob(job: ImportJobStatus): TaskListItem | null {
  if (!job.taskNo) return null;
  return {
    taskNo: job.taskNo,
    fileNo: job.file?.fileNo,
    sourceFileName: job.file?.sourceFileName,
    fileType: job.file?.fileType,
    status: job.status === "FAIL" ? "FAIL" : "INIT",
    stage: job.stage ?? "等待处理",
    progress: job.status === "SUCCESS" ? 0 : job.progress,
    errorMsg: job.errorMessage,
    createdAt: new Date().toISOString(),
  };
}

export function UploadPage({ publicHome = false }: { publicHome?: boolean }) {
  const [searchParams] = useSearchParams();
  const defaultMode = searchParams.get("mode") === "link" ? "link" : "file";
  const { showToast } = useToast();
  const user = useAuthStore((state) => state.user);
  const experience = useQuery({ queryKey: ["public", "experience"], queryFn: getExperience });
  const draft = readUploadDraft();
  const resumable = draft?.ownerUid === user?.uid && Boolean(draft?.fileNo);
  const [mode, setMode] = useState<"file" | "link">(defaultMode);
  const [file, setFile] = useState<File | null>(null);
  const [douyinLink, setDouyinLink] = useState(() => readUploadDraft()?.link || "");
  const [localResult, setLocalResult] = useState<LocalUploadResult | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [lastImportJob, setLastImportJob] = useState<ImportJobStatus | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async (targetFile: File | null) => {
      await ensureExperience();
      const currentUser = useAuthStore.getState().user;
      const pending = readUploadDraft();
      const uploaded = pending?.fileNo && pending.ownerUid === currentUser?.uid
        ? { fileNo: pending.fileNo, sourceFileName: pending.sourceFileName || "已上传素材" }
        : await uploadFile(targetFile!);
      saveUploadDraft({ fileNo: uploaded.fileNo, sourceFileName: uploaded.sourceFileName, ownerUid: currentUser?.uid });
      const task = await createTask(uploaded.fileNo);
      return { fileNo: uploaded.fileNo, taskNo: task.taskNo, sourceFileName: uploaded.sourceFileName };
    },
    onSuccess: (result) => {
      clearUploadDraft();
      setLocalResult(result);
      upsertTaskCache(queryClient, taskFromLocalResult(result));
      void queryClient.invalidateQueries({ queryKey: ["tasks"], refetchType: "active" });
      showToast({ tone: "success", title: "已开始处理", description: "完成后可以在处理记录里查看文稿。" });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "暂时无法处理", description: error.message });
    },
  });

  const importMutation = useMutation({
    mutationFn: async (text: string) => { await ensureExperience(); return createImportJob(text); },
    onSuccess: (result) => {
      setActiveJobId(result.jobId);
      setLastImportJob({ jobId: result.jobId, status: result.status, progress: 0, stage: "正在读取链接" });
      showToast({ tone: "info", title: "链接已提交", description: "我们会在后台下载并提取文字，你可以先离开页面。" });
    },
    onError: (error) => {
      showToast({ tone: "error", title: "链接提交失败", description: error.message });
    },
  });

  const importJobQuery = useQuery({
    queryKey: ["file", "import-link", activeJobId],
    queryFn: () => getImportJob(activeJobId!),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => {
      const data = query.state.data as ImportJobStatus | undefined;
      return isTerminalStatus(data?.status) ? false : 1600;
    },
  });

  const importJob = importJobQuery.data ?? lastImportJob;

  useEffect(() => {
    const data = importJobQuery.data;
    if (!data) return;

    setLastImportJob(data);
    if (data.status === "FAIL" && data.file?.fileNo && data.errorMessage?.includes("额度")) {
      saveUploadDraft({ fileNo: data.file.fileNo, sourceFileName: data.file.sourceFileName, ownerUid: useAuthStore.getState().user?.uid });
      if (useAuthStore.getState().user?.guest) window.dispatchEvent(new CustomEvent("guest:required", { detail: data.errorMessage }));
    }
    const task = taskFromImportJob(data);
    if (task) {
      upsertTaskCache(queryClient, task);
    }

    if (!isTerminalStatus(data.status)) {
      if (data.taskNo) {
        patchTaskCache(queryClient, {
          taskNo: data.taskNo,
          stage: "正在处理",
          progress: data.progress,
          errorMsg: data.errorMessage,
        });
      }
      return;
    }

    setActiveJobId(null);
    void queryClient.invalidateQueries({ queryKey: ["tasks"], refetchType: "active" });
    if (data.status === "SUCCESS") {
      showToast({ tone: "success", title: "链接处理已开始", description: "下载完成，正在为你提取文字。" });
    } else {
      showToast({ tone: "error", title: "链接处理失败", description: data.errorMessage ?? "请稍后重试。" });
    }
  }, [importJobQuery.data, showToast]);

  const selectedFileLabel = useMemo(() => {
    if (!file) return "选择音频或视频文件";
    return `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  }, [file]);

  function handleLocalSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file && !resumable) {
      showToast({ tone: "warning", title: "请先选择文件", description: "支持常见音频和视频格式。" });
      return;
    }
    uploadMutation.mutate(file);
  }

  function handleLinkSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sourceText = douyinLink.trim();
    if (!sourceText) {
      showToast({ tone: "warning", title: "请粘贴抖音链接", description: "完整分享文案也可以，我们会自动识别链接。" });
      return;
    }
    importMutation.mutate(sourceText);
  }

  return (
    <div className="page-stack">
      <section className={`upload-hero${publicHome ? " upload-hero--public" : ""}`}>
        <div>
          <Badge tone="success">{publicHome ? "音视频转文字" : "开始提取"}</Badge>
          <h1>{publicHome ? <>把声音，<span className="public-home-title">整理成文字。</span></> : "上传素材，稍等片刻拿到文字稿。"}</h1>
          {!user || user.guest ? <p>{experience.data?.enabled
            ? `免注册体验 ${experience.data.points} 点，约可处理 ${Math.floor(experience.data.points * experience.data.secondsPerPoint / 60)} 分钟音频。上传文件或粘贴抖音链接即可开始。`
            : experience.isError ? "上传音视频或粘贴抖音链接，体验信息暂时无法加载，可稍后重试或登录。" : "上传音视频或粘贴抖音链接，生成可复制的文字稿。"}</p>
            : <p>系统会先预估时长和所需额度，完成后可直接复制文字稿。</p>}
        </div>
        <div className="mode-switch">
          <Button type="button" variant={mode === "file" ? "secondary" : "ghost"} icon={<UploadCloud size={16} />} onClick={() => setMode("file")}>
            本地文件
          </Button>
          <Button type="button" variant={mode === "link" ? "secondary" : "ghost"} icon={<Link2 size={16} />} onClick={() => setMode("link")}>
            抖音链接
          </Button>
        </div>
      </section>

      <section className="upload-grid">
        <Card title={mode === "file" ? "上传本地文件" : "粘贴抖音链接"} eyebrow="选择来源">
          {resumable ? <p>已保留素材：{draft?.sourceFileName}。点击开始提取即可继续，无需重新上传。</p> : null}
          {mode === "file" ? (
            <form className="upload-form" onSubmit={handleLocalSubmit}>
              <label className="upload-drop">
                <FileAudio2 size={30} />
                <strong>{selectedFileLabel}</strong>
                <span>支持 mp3、wav、m4a、mp4、mov、webm 等常见格式</span>
                <input type="file" accept="audio/*,video/*" onChange={(event) => { setFile(event.target.files?.[0] ?? null); clearUploadDraft(); }} />
              </label>
              <Button type="submit" loading={uploadMutation.isPending} icon={<UploadCloud size={18} />}>
                开始提取文字
              </Button>
            </form>
          ) : (
            <form className="upload-form" onSubmit={handleLinkSubmit}>
              <div className="upload-link-drop">
                <Link2 size={30} />
                <strong>粘贴抖音分享链接</strong>
                <span>链接或完整分享文案都可以，我们会自动识别</span>
                <Input
                  aria-label="抖音分享链接"
                  value={douyinLink}
                  onChange={(event) => { setDouyinLink(event.target.value); saveUploadDraft({ link: event.target.value, ownerUid: user?.uid }); }}
                  placeholder="https://v.douyin.com/..."
                />
              </div>
              <Button type="submit" loading={importMutation.isPending} icon={<Link2 size={18} />}>
                提交链接
              </Button>
            </form>
          )}
        </Card>

        <Card title={publicHome && !localResult && !importJob ? "文字稿示例" : "当前进度"} eyebrow={publicHome ? "提取效果" : "处理状态"}>
          {uploadMutation.isPending ? (
            <div className="inline-status">
              <LoadingSkeleton lines={3} />
              <p>正在上传并检查文件，请保持页面打开几秒钟。</p>
            </div>
          ) : localResult ? (
            <div className="success-panel">
              <CheckCircle2 size={28} />
              <div>
                <strong>{localResult.sourceFileName}</strong>
                <p>已开始处理，完成后会生成可复制文字。</p>
                <Link className="text-link" to={`/tasks/${localResult.taskNo}`}>
                  查看处理进度
                </Link>
              </div>
            </div>
          ) : importJob ? (
            <div className="import-status">
              <div className="import-status__top">
                <Badge tone={importJob.status === "FAIL" ? "danger" : importJob.status === "SUCCESS" ? "success" : "warning"}>
                  {importJob.status === "FAIL" ? "处理失败" : importJob.status === "SUCCESS" ? "已开始提取" : "正在处理"}
                </Badge>
                <span>{importJob.progress}%</span>
              </div>
              <div className="progress-track">
                <span style={{ width: `${Math.max(0, Math.min(importJob.progress, 100))}%` }} />
              </div>
              <p>{importJob.status === "FAIL" ? "没有成功读取这个链接" : "正在读取链接并准备文字提取"}</p>
              {importJob.taskNo ? (
                <Link className="text-link" to={`/tasks/${importJob.taskNo}`}>
                  查看处理进度
                </Link>
              ) : (
                <Link className="text-link" to="/tasks">
                  查看处理记录
                </Link>
              )}
              {importJob.errorMessage ? <p className="error-text">{importJob.errorMessage}</p> : null}
              {importJob.errorMessage?.includes("额度不足") ? <Link className="text-link" to="/payment">前往支付宝购买额度</Link> : null}
            </div>
          ) : (
            publicHome ? <div className="page-stack"><Badge tone="info">示例内容</Badge><p>今天我们讨论了项目的下一步安排：先完成素材整理，再根据访谈内容梳理重点，下周提交初稿。</p>
              <p className="muted-text">课程、访谈、会议、短视频，提取后可直接复制完整文字稿。</p>
              {experience.data?.sessionDays ? <p className="muted-text">免注册记录保存 {experience.data.sessionDays} 天，注册可保留文字稿。</p> : null}</div>
              : <EmptyState title="还没有提交素材" description="选择一个本地文件，或粘贴抖音链接后，这里会显示处理进度。" />
          )}
        </Card>
      </section>
    </div>
  );
}
