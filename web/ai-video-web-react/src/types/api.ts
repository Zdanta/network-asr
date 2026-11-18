export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export type LoginPayload = {
  email: string;
  code: string;
  inviteCode?: string;
};

export type LoginResult = {
  guestConverted?: boolean;
  email: string | null;
  token: string;
  uid: string;
  userId: number;
  mobile: string | null;
  nickname: string | null;
  inviteCode: string;
  remainingPoints: number;
  remainingCount?: number;
  admin?: boolean;
};

export type UserInfo = {
  guest?: boolean;
  email: string | null;
  uid: string;
  userId: number;
  mobile: string | null;
  nickname: string | null;
  inviteCode: string;
  vipExpireTime?: string | null;
  remainingPoints: number;
  remainingCount: number;
  admin: boolean;
};

export type HealthInfo = {
  status: string;
  appName: string;
  appVersion: string;
  database?: {
    status: string;
    latencyMs: number;
  };
};

export type QuotaInfo = {
  remainingPoints: number;
  remainingCount: number;
  localRemainingPoints: number;
  purchasedRemainingPoints: number;
  vip: boolean;
  vipExpireTime?: string | null;
  secondsPerPoint: number;
  pointsPerMinute: number;
};

export type TaskListItem = {
  taskNo: string;
  fileNo?: string | null;
  sourceFileName?: string | null;
  fileType?: string | null;
  status: "INIT" | "PROCESSING" | "SUCCESS" | "FAIL" | string;
  stage?: string | null;
  progress: number;
  rawText?: string | null;
  errorMsg?: string | null;
  durationSeconds?: number | null;
  estimatedPoints?: number | null;
  createdAt?: string | null;
  finishTime?: string | null;
};

export type FileUploadResult = {
  fileNo: string;
  fileUrl: string;
  sourceFileName: string;
  fileType: string;
  fileSize: number;
  cookieSource?: string | null;
  downloadEngine?: string | null;
};

export type TaskCreateResult = {
  taskNo: string;
};

export type TaskDeleteResult = {
    taskNo: string;
    deleted: boolean;
};

export type SourceDownloadTicket = {
  url: string;
  expiresAt: string;
};

export type TaskPageResult = {
  pageNo: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  records: TaskListItem[];
};

export type TaskStatusResult = {
  taskNo: string;
  sourceFileName?: string | null;
  status: "INIT" | "PROCESSING" | "SUCCESS" | "FAIL" | string;
  stage?: string | null;
  progress: number;
  errorMsg?: string | null;
  durationSeconds?: number | null;
  estimatedPoints: number;
  secondsPerPoint: number;
  pointsPerMinute: number;
  sourceDownloadAvailable?: boolean;
  sourceDownloadExpiresAt?: string | null;
  sourceDownloadUrl?: string | null;
};

export type TaskResult = TaskStatusResult & {
  rawText?: string | null;
};

export type PaymentProductType = "FIRST_RECHARGE_GIFT" | "POINT_PACK" | "POINT_PACK_PLUS";

export type PaymentOrderCreateResult = {
  orderNo: string;
  productType: PaymentProductType | string;
  productName: string;
  amount: string;
  status: string;
  payUrl: string;
  qrCode: string;
};

export type PaymentOrderInfo = {
  orderNo: string;
  productType: PaymentProductType | string;
  amount: string;
  status: string;
  paidAt?: string | null;
};

export type PaymentNotifyResult = {
  orderNo?: string | null;
  status: string;
};

export type InviteInfo = {
  rewardRatePercent: number;
  holdDays: number;
  inviteCode: string;
  inviteCount: number;
  rewardTotal: string;
};

export type InviteRecord = {
  inviteeUid: string;
  rewardType: string;
  rewardValue: number;
  rechargeAmount: string;
  rewardAmount: string;
  rewardStatus: string;
  triggerOrderNo?: string | null;
  createdAt?: string | null;
};

export type WithdrawalSummary = {
  frozenRewardAmount: string;
  debtAmount: string;
  rewardTotal: string;
  pendingAmount: string;
  paidAmount: string;
  withdrawableAmount: string;
  minWithdrawalAmount: string;
  canApply: boolean;
};

export type WithdrawalRecord = {
  withdrawNo: string;
  amount: string;
  alipayAccount: string;
  status: string;
  statusDesc: string;
  remark?: string | null;
  createdAt?: string | null;
  handledAt?: string | null;
  paidAt?: string | null;
};

export type QuotaLog = {
  changeType: string;
  changeTypeDesc: string;
  changeAmount: number;
  afterPoints: number | null;
  bizNo?: string | null;
  remark?: string | null;
  createdAt: string;
};

export type QuotaLogPage = {
  records: QuotaLog[];
  total: number;
  pageNo: number;
  pageSize: number;
  pages: number;
};

export type AdminDashboardOverview = {
  totalUsers: number;
  todayNewUsers: number;
  todayTasks: number;
  todaySuccessTasks: number;
  todayFailTasks: number;
  todayPaidOrders: number;
  todayPaidAmount: string;
  pendingFailTasks: number;
  pendingWithdrawals: number;
  pendingWithdrawalAmount: string;
};

export type AdminOrder = {
  source: "OPCPAY" | "LEGACY";
  orderNo: string;
  userUid: string | null;
  email: string | null;
  nickname: string | null;
  productName: string;
  amount: string | null;
  quantity: number | null;
  status: "PAID" | "PENDING" | "FAILED" | "CLOSED" | "REFUNDED" | "UNKNOWN";
  channel: string;
  createdAt: string;
  paymentConfirmedAt: string | null;
  checkedAt: string | null;
};

export type AdminOrderPage = { records: AdminOrder[]; total: number; pageNo: number; pageSize: number; hasMore: boolean };

export type AdminUser = {
  uid: string;
  mobile?: string | null;
  email?: string | null;
  nickname?: string | null;
  inviteCode: string;
  status: string;
  remainingPoints: number;
  localRemainingPoints: number;
  purchasedRemainingPoints: number;
  taskCount: number;
  paidOrderCount: number;
  createdAt?: string | null;
};

export type AdminUserPage = {
  pageNo: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  records: AdminUser[];
};

export type AdminUserDetail = AdminUser & {
  inviterUid?: string | null;
  vipExpireTime?: string | null;
  inviteCount: number;
};

export type AdminWithdrawal = {
  withdrawNo: string;
  userUid?: string | null;
  mobile?: string | null;
  email?: string | null;
  nickname?: string | null;
  amount: string;
  alipayAccount: string;
  status: "PENDING" | "PAID" | "REJECTED" | string;
  statusDesc: string;
  remark?: string | null;
  handledBy?: number | null;
  createdAt?: string | null;
  handledAt?: string | null;
  paidAt?: string | null;
};

export type AdminWithdrawalPage = {
  pageNo: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  records: AdminWithdrawal[];
};

export type ImportJobFile = {
  fileNo: string;
  fileUrl: string;
  sourceFileName: string;
  fileType: string;
  fileSize: number;
  cookieSource?: string | null;
  downloadEngine?: string | null;
};

export type ImportJobCreateResult = {
  jobId: string;
  status: string;
};

export type ImportJobStatus = {
  jobId: string;
  status: "INIT" | "PROCESSING" | "SUCCESS" | "FAIL" | string;
  progress: number;
  stage?: string | null;
  file?: ImportJobFile | null;
  taskNo?: string | null;
  errorMessage?: string | null;
};
