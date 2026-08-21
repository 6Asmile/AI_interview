---
title: 代码 API 数据事实索引
type: generated-facts
order: 9
status: generated
implementation_status: implemented
updated: 2026-08-12
last_verified: 2026-08-12
verified_commit: 89313f8268e96d79b6968b39846f319c0892f50c
audience:
  - engineer
  - interviewer
related_code:
  - ai_interview_backend
  - ai-interview-frontend
  - ai-interview-admin
  - docker-compose.infra.yml
tags:
  - generated
  - code-facts
  - api-index
---

# 代码、API、数据事实索引

> 本文由 `scripts/build_project_facts.py` 从当前仓库生成，只列可机械提取的事实；它不能替代六卷中的设计解释。

## 基线

- Commit：`89313f8268e96d79b6968b39846f319c0892f50c`
- 最近提交：2026-08-12T16:48:56+08:00 feat: 完善可靠异步底座与项目验证能力
- Django 数据模型应用：15
- Django model classes：152
- HTTP router/path declarations：209
- Candidate/Staff route paths：62
- Celery shared tasks：35
- 测试入口文件：40

## Django 应用与模型

| 应用 | 模型 | 命名约束/索引名称 |
|---|---|---|
| `blog` | `Category`, `Tag`, `Post`, `Comment`, `DailyPostStats` | `comment`, `comment_action`, `comments`, `daily_stats`, `post`, `posts`, `replies`, `作者`, `分类`, `分类名称`, `分类描述`, `字数`, `封面图`, `当日浏览量`, `当日点赞量`, `所属文章`, `收藏数`, `文章内容 (Markdown)`, `文章摘要`, `文章标题`, `文章状态`, `日期`, `是否精选`, `标签`, `标签名称`, `浏览量`, `点赞数`, `父评论`, `评论内容 (Markdown)`, `评论数`, `评论者`, `预定发布时间` |
| `careers` | `CareerFact`, `JobTarget`, `JobApplication`, `ApplicationEvent`, `LearningTask`, `CareerProfile`, `SkillTaxonomy`, `SkillEvidence`, `AbilitySnapshot`, `Company`, `CompanyVerification`, `CompanyMember`, `JobPosting`, `JobPostingRevision`, `JobMatchAnalysis`, `LearningPlan`, `CareerTimelineEvent`, `WeeklyCareerReport` | `+`, `ability_snapshots`, `applications`, `career_facts`, `career_learning_plans`, `career_learning_tasks`, `career_profile`, `career_timeline_events`, `company_memberships`, `created_companies`, `created_job_postings`, `events`, `evidence`, `job_applications`, `job_match_analyses`, `job_match_analysis`, `job_postings`, `job_targets`, `learning_plans`, `learning_tasks`, `match_analyses`, `members`, `revisions`, `saved_targets`, `skill_evidence`, `skill_evidence_proficiency_range`, `tasks`, `uniq_career_timeline_dedup`, `uniq_company_member`, `uniq_job_posting_revision`, `uniq_skill_evidence_source`, `uniq_weekly_career_report`, `verifications`, `weekly_career_reports` |
| `chat` | `Conversation`, `Message`, `ConversationParticipantState`, `MessageAttachment`, `UserBlock`, `MessageReport`, `ChatOutbox` | `+`, `attachments`, `blocked_by_users`, `blocked_users`, `chat_attachments`, `conversation_states`, `conversations`, `created_conversations`, `message_reports`, `messages`, `outbox_events`, `participant_states`, `replies`, `reports`, `sent_messages`, `support_conversations`, `uniq_chat_client_message`, `uniq_conversation_participant_state`, `uniq_message_report`, `uniq_user_block` |
| `community` | `CommunityIdentity`, `CommunityTopicLink`, `CommunityWebhookEvent`, `Topic`, `CommunityContent`, `ContentRevision`, `CommunityComment`, `Reaction`, `Bookmark`, `TopicFollow`, `UserFollow`, `ContentDailyMetric`, `SharedArtifactSnapshot`, `ContentReport`, `ModerationCase`, `ModerationDecision`, `Appeal`, `ReputationLedger`, `GrowthEvent`, `StreakState`, `Challenge`, `ChallengeEnrollment` | `+`, `appeals`, `bookmarks`, `challenge_enrollments`, `comments`, `community_bookmarks`, `community_comments`, `community_contents`, `community_identity`, `community_reactions`, `community_reports`, `community_topic`, `contents`, `daily_metrics`, `decisions`, `enrollments`, `followed_community_topics`, `followers`, `growth_events`, `growth_streak`, `moderation_appeals`, `moderation_cases`, `native_followers`, `native_following`, `reactions`, `replies`, `reports`, `reputation_entries`, `revisions`, `shared_artifact_snapshots`, `uniq_challenge_enrollment`, `uniq_community_bookmark`, `uniq_community_content_daily_metric`, `uniq_community_content_revision`, `uniq_community_legacy_source_id`, `uniq_community_reaction`, `uniq_community_report_reason`, `uniq_community_topic_follow`, `uniq_community_user_follow` |
| `core` | `IdempotencyRecord`, `AsyncOperation`, `OperationDispatchOutbox`, `OperationEvent`, `IntegrationOutbox`, `ConsumerInbox`, `RuntimePolicy` | `async_operations`, `core_opdisp_ready_idx`, `core_opevent_time_idx`, `dispatches`, `events`, `idempotency_claims`, `idempotency_records`, `operation_active_requires_lease`, `operation_attempt_within_limit`, `operation_progress_valid`, `operation_terminal_has_completed_at`, `uniq_consumer_inbox_event`, `uniq_operation_business_idempotency`, `uniq_operation_dispatch_fence`, `uniq_operation_event_sequence`, `uniq_user_idempotency_scope_key` |
| `interactions` | `Like`, `Bookmark`, `Follow` | `bookmarked_by`, `bookmarks`, `follower_relations`, `following_relations`, `likes` |
| `interviews` | `AgentConfigProfile`, `AgentConfigRevision`, `AgentPromptTemplate`, `AgentConfigKnowledgeBinding`, `AgentConfigEvaluationRun`, `InterviewRubric`, `RubricDimension`, `RubricLevelAnchor`, `InterviewTemplate`, `InterviewTemplateStage`, `InterviewCalibrationCase`, `InterviewSession`, `InterviewQuestion`, `InterviewQuestionGenerationJob`, `InterviewAgentRun`, `InterviewAgentExecution`, `InterviewAgentDispatch`, `InterviewReferenceAnswer`, `InterviewAgentNodeRun`, `InterviewAgentTrace`, `InterviewAgentToolCall`, `InterviewAgentMemoryEvent`, `InterviewMediaArtifact`, `EvaluationDataset`, `EvaluationCase`, `EvaluationRun`, `EvaluationRunMetric` | `+`, `AI 反馈内容`, `Agent Loop轮次`, `Agent引擎`, `Agent运行`, `Agent配置快照`, `Agent配置覆盖`, `Checkpoint命名空间`, `JD`, `JD 快照`, `LangGraph Run ID`, `LangGraph Thread ID`, `Prompt版本`, `RAG来源`, `RAG题库上下文`, `agent_config_bindings`, `agent_config_evaluation_runs`, `agent_config_overrides`, `agent_executions`, `agent_memory_events`, `agent_prompt_templates`, `agent_runs`, `agent_tool_calls`, `agent_traces`, `anchors`, `approved_agent_config_revisions`, `baseline_config_evaluation_runs`, `calibration_cases`, `cases`, `config_evaluation_runs`, `created_agent_config_profiles`, `created_agent_config_revisions`, `derived_revisions`, `dimensions`, `dispatch`, `evaluation_datasets`, `evaluation_run`, `evaluation_runs`, `execution`, `generation_jobs`, `interview_agent_execution`, `interview_calibration_cases`, `interview_media_artifacts`, `interview_reference_answers`, `interview_rubrics`, `interview_sessions`, `interview_templates`, `interviews_status_lease_idx`, `knowledge_bindings`, `media_artifacts`, `memory_events`, `metrics`, `next_generation_jobs`, `node_runs`, `prompts`, `question_generation_jobs`, `questions`, `reference_answers`, `result_agent_executions`, `revisions`, `run_metrics`, `runs`, `sessions`, `stages`, `templates`, `tool_calls`, `traces`, `uniq_agent_config_knowledge_binding`, `uniq_agent_config_revision`, `uniq_agent_execution_idempotency`, `uniq_agent_prompt_task_revision`, `uniq_interview_agent_node_attempt`, `uniq_interview_agent_run_request`, `uniq_interview_generation_job_sequence`, `uniq_interview_memory_event_dedup`, `uniq_interview_question_sequence`, `uniq_interview_reference_answer_snapshot`, `uniq_platform_agent_config_profile`, `上下文预算`, `业务事件`, `主导SubAgent`, `事件`, `会话 UUID`, `体验模式`, `候选人反问预留时长`, `允许返回上层话题`, `允许题型`, `关联简历`, `关联轨迹`, `关联问题`, `兼容运行记录`, `出题指引`, `创建时间`, `匿名化真实回答`, `匿名化简历`, `压缩上下文摘要`, `参考答案/真值`, `召回次数`, `回答时间`, `回答评估摘要`, `回答音频 URL`, `实时分析数据`, `岗位`, `岗位匹配关键词`, `工具名称`, `已回答问题`, `已覆盖话题`, `幂等请求哈希`, `幂等键`, `平台异步操作`, `开始时间`, `异常保护最大轮次`, `当前面试阶段`, `待追问话题`, `得分`, `感知摘要`, `所属会话`, `所属用户`, `执行栅栏令牌`, `持久化状态摘要`, `持续时间 (秒)`, `指标值`, `指标名称`, `指标详情`, `排序`, `无关文档修订`, `无答案样例`, `是否启用`, `是否开启录像`, `是否强制要求知识库依据`, `更新时间`, `最低分`, `最低覆盖次数`, `最低验证能力数`, `最后召回时间`, `最后持久化事件序号`, `最后活动时间`, `最少有效轮次`, `最短时长（分钟）`, `最终生成文本`, `最终问题`, `最近心跳时间`, `最长时长（分钟）`, `最高分`, `期望主题`, `期望命中的文档修订`, `期望能力标签`, `期望评分`, `期望追问方向`, `本场面试计划快照`, `权重`, `权限范围`, `来源节点`, `校准样例标题`, `校验状态`, `校验错误`, `检索上下文`, `检索轨迹`, `模型配置快照`, `模板名称`, `模板快照`, `模板说明`, `模板配置`, `求职目标`, `版本`, `状态`, `状态版本`, `生成模式`, `生成的问题`, `生成结果问题`, `用户回答文本`, `目标岗位`, `目标时长（分钟）`, `目标能力维度`, `目标题号`, `真实匿名化回答`, `短期记忆摘要`, `租约持有者`, `租约过期时间`, `等级`, `等级描述`, `简历快照`, `简历版本快照来源`, `结束时间`, `维度名称`, `维度标识`, `维度说明`, `耗时毫秒`, `能力覆盖汇总`, `节点名称`, `节点输出`, `规则评分配置`, `视频上传任务`, `触发问题`, `记忆去重键`, `记忆摘要`, `记忆键`, `评估摘要`, `评估数据集名称`, `评估时间`, `说明`, `请求哈希`, `调用SubAgent`, `输入哈希`, `输入摘要`, `输出摘要`, `过期时间`, `进入条件`, `进度计算模式`, `退出条件`, `部分生成文本`, `配置快照`, `重要性`, `重试次数`, `量表名称`, `量表说明`, `错误信息`, `问题`, `问题内容`, `问题序号`, `问题数量`, `阶段`, `阶段名称`, `阶段最短时长（分钟）`, `阶段最长时长（分钟）`, `阶段标识`, `降级原因`, `难度`, `面试会话`, `面试报告`, `面试模式`, `面试模板`, `面试风格配置`, `题目生成计划`, `题目计划`, `题目语义签名`, `题量占比` |
| `knowledge` | `RetrievalProfile`, `RetrievalProfileRevision`, `KnowledgeDocument`, `KnowledgeBase`, `KnowledgeBaseRevision`, `KnowledgeBaseRevisionDocument`, `KnowledgeDocumentRevision`, `KnowledgeChunkDraft`, `KnowledgeImportBatch`, `KnowledgeImportFile`, `KnowledgeChunk` | `+`, `Embedding模型`, `Token数量估算`, `approved_knowledge_base_revisions`, `approved_knowledge_documents`, `approved_knowledge_revisions`, `approved_retrieval_profile_revisions`, `child_chunks`, `children`, `chunk_drafts`, `chunks`, `created_knowledge_base_revisions`, `created_knowledge_bases`, `created_retrieval_profile_revisions`, `created_retrieval_profiles`, `document_bindings`, `documents`, `import_files`, `knowledge_base_bindings`, `knowledge_base_revisions`, `knowledge_documents`, `knowledge_import_batches`, `knowledge_revisions`, `published_chunks`, `revisions`, `uniq_knowledge_base_revision`, `uniq_knowledge_base_revision_document`, `uniq_knowledge_document_revision`, `uniq_knowledge_revision_chunk_index`, `uniq_knowledge_revision_chunk_order`, `uniq_retrieval_profile_revision`, `上传人`, `上传文件`, `内容哈希`, `分片内容`, `分片层级`, `分片序号`, `分片数量`, `创建人`, `原始文件名`, `发布版本`, `可见范围`, `员工审批人`, `块类型`, `处理状态`, `失败数`, `审批人`, `审批状态`, `审批通过时间`, `导入批次`, `导入状态`, `导入选项`, `当前发布版本`, `当前编辑版本`, `成功数`, `所属文档`, `拒绝原因`, `提交审核时间`, `文件总数`, `文件类型`, `文档标题`, `是否启用OCR`, `最后检索命中时间`, `最后索引时间`, `来源类型`, `标题路径`, `检索元数据`, `检索命中次数`, `源文件`, `源文件列表`, `父级分片`, `生成文档`, `知识内容`, `索引时间`, `索引状态`, `结束页`, `结构化解析结果`, `能力标签`, `解析器`, `解析器版本`, `解析状态`, `解析降级原因`, `语义组`, `起始页`, `适用岗位`, `错误信息`, `错误日志`, `难度` |
| `notifications` | `Notification`, `NotificationOutbox` | `+`, `notification_action_objects`, `notification_actors`, `notification_outbox_events`, `notification_targets`, `notifications`, `outbox_event`, `接收者`, `是否已读`, `通知类型` |
| `reports` | `ResumeAnalysisReport` | `AI分析报告JSON`, `analysis_reports`, `resume_analysis_reports`, `模型配置快照`, `目标岗位JD`, `目标岗位来源`, `简历版本快照`, `简历版本快照来源`, `综合匹配度得分`, `证据来源` |
| `resumes` | `Resume`, `ResumeVersion`, `ResumeDraft`, `ResumeDesignRevision`, `ResumeEvidenceLink`, `ResumeAsset`, `ResumeArtifact`, `ResumeQualityReport`, `ResumeShareLink`, `ResumeShareAccess`, `ResumeImportJob`, `ResumeOperationRequest`, `ResumeSuggestion`, `ResumeVariant`, `Education`, `WorkExperience`, `ProjectExperience`, `Skill` | `+`, `JSON Patch`, `JSON Resume 版本`, `accesses`, `artifact`, `artifacts`, `assets`, `children`, `design_revisions`, `draft`, `drafts`, `educations`, `evidence_links`, `iFaceoff 布局 JSON`, `import_jobs`, `operation_requests`, `project_experiences`, `quality_reports`, `resume_design_revisions`, `resume_drafts`, `resume_evidence_links`, `resume_import_jobs`, `resume_operation_requests`, `resume_opreq_owner_idx`, `resume_opreq_target_required`, `resume_share_links`, `resume_suggestions`, `resume_variants`, `resume_versions`, `resumes`, `share_links`, `skills`, `suggestions`, `uniq_default_resume_per_user`, `uniq_resume_design_revision`, `uniq_resume_evidence_pointer_fact`, `uniq_resume_version_number`, `variant_outputs`, `variants`, `versions`, `work_experiences`, `上传的简历文件`, `专业`, `个人总结`, `公司名称`, `创建时间`, `城市`, `姓名`, `学位`, `学校名称`, `工作描述`, `开始日期`, `当前版本`, `当前设计版本`, `所属用户`, `所属简历`, `技能名称`, `担任角色`, `旧版优化建议`, `旧版编辑器 JSON`, `是否默认简历`, `更新时间`, `期望职位`, `标准简历 JSON`, `模板名称`, `熟练度`, `状态`, `电话`, `简历标题`, `结束日期`, `职业事实证据快照`, `职位`, `解析后的文本内容`, `邮箱`, `项目名称`, `项目描述` |
| `staff_admin` | `StaffRole`, `StaffSession`, `StaffMFADevice`, `StaffInvitation`, `StaffRecoveryCode`, `StaffEmailOutbox`, `BreakGlassGrant`, `AdminIdempotencyRecord`, `AdminAuditEvent`, `PlatformFeatureFlag`, `MaintenanceNotice` | `+`, `accounts`, `audit_events`, `break_glass_grants`, `email_events`, `idempotency_records`, `invitation`, `maintenance_notices`, `mfa_devices`, `recovery_codes`, `sent_invitations`, `sessions`, `staff_idempotency_scope_key`, `uniq_staff_recovery_code` |
| `system` | `AIModel`, `AISetting`, `Industry`, `JobPosition`, `ProviderCredential`, `ModelDeployment`, `ModelAlias`, `RoutePolicy`, `RoutePolicyTarget`, `UsageBudget`, `ModelRequestLedger`, `ModelAttempt` | `API Base URL`, `API Key`, `API Keys 映射`, `ai_setting`, `asr_settings`, `attempts`, `chat_settings`, `credentials`, `deployments`, `embedding_settings`, `job_positions`, `legacy_settings`, `model_attempts`, `model_request_ledgers`, `model_usage_budget`, `provider_credentials`, `request_ledgers`, `rerank_settings`, `route_policy`, `route_targets`, `targets`, `tts_settings`, `uniq_model_request_attempt`, `uniq_policy_deployment`, `创建时间`, `向量维度`, `图标 SVG 代码`, `岗位名称`, `岗位描述`, `所属用户`, `所属行业`, `排序`, `支持 JSON 模式`, `是否启用`, `更新时间`, `模型供应商`, `模型描述`, `模型显示名称`, `模型类型`, `模型调用标识`, `行业名称`, `行业描述`, `默认AI模型`, `默认ASR模型`, `默认Embedding模型`, `默认Rerank模型`, `默认TTS模型`, `默认对话模型` |
| `users` | `NotificationPreference`, `AuthSession`, `LoginAudit`, `OAuthFlow`, `PrivacyRequest` | `auth_sessions`, `login_audits`, `notification_preference`, `oauth_flows`, `privacy_requests`, `users_user_email_ci_unique`, `users_user_username_ci_unique`, `头像`, `工作年限`, `所在地区`, `所属企业`, `手机号`, `技能画像`, `新手引导完成时间`, `新手引导步骤`, `更新时间`, `求职状态`, `状态`, `目标岗位`, `职业标题`, `角色`, `资料可见性`, `邮箱` |
| `video_uploads` | `FileUploadTask`, `FileChunk`, `VideoTranscodeTask` | `chunks`, `transcode_task`, `transcode_tasks`, `upload_tasks`, `上传时间`, `临时存储路径`, `关联上传任务`, `分片MD5`, `分片大小(字节)`, `分片序号`, `创建时间`, `原始文件名`, `原始文件大小(字节)`, `原始文件路径`, `原始视频时长(秒)`, `合并后文件路径`, `完成时间`, `已上传分片数`, `开始处理时间`, `总分片数`, `所属上传任务`, `所属用户`, `文件唯一标识`, `文件总大小(字节)`, `更新时间`, `状态`, `视频质量CRF值`, `视频降噪`, `视频降噪参数`, `转码后文件大小(字节)`, `转码后文件路径`, `转码进度(0-100)`, `错误信息`, `音频降噪`, `音频降噪参数` |

## 后端 HTTP 路由声明

| 文件:行 | 声明 |
|---|---|
| `ai_interview_backend/ai_interview_backend/urls.py:21` | `path('internal/django-admin/', admin.site.urls)` |
| `ai_interview_backend/ai_interview_backend/urls.py:22` | `path('internal/metrics', InternalMetricsView.as_view(), name='internal-metrics')` |
| `ai_interview_backend/ai_interview_backend/urls.py:23` | `path('api/admin/v1/', include('staff_admin.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:26` | `path('api/v1/', include([` |
| `ai_interview_backend/ai_interview_backend/urls.py:27` | `path('auth/', include('users.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:28` | `path('auth/login/', AuditedTokenObtainPairView.as_view(), name='token_obtain_pair')` |
| `ai_interview_backend/ai_interview_backend/urls.py:29` | `path('auth/token/refresh/', AuditedTokenRefreshView.as_view(), name='token_refresh')` |
| `ai_interview_backend/ai_interview_backend/urls.py:30` | `path('', include('core.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:31` | `path('', include('resumes.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:32` | `path('', include('interviews.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:33` | `path('', include('system.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:34` | `path('', include('blog.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:35` | `path('', include('community.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:36` | `path('', include('interactions.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:37` | `path('', include('notifications.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:38` | `path('', include('chat.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:39` | `path('', include('video_uploads.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:40` | `path('', include('knowledge.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:42` | `path('upload/', FileUploadView.as_view(), name='file-upload')` |
| `ai_interview_backend/ai_interview_backend/urls.py:43` | `path('', include('reports.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:44` | `path('generate-resume/', GenerateResumeView.as_view(), name='generate-resume')` |
| `ai_interview_backend/ai_interview_backend/urls.py:46` | `path('accounts/', include('allauth.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:47` | `path('api/v2/', include([` |
| `ai_interview_backend/ai_interview_backend/urls.py:48` | `path('', include('careers.urls'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:49` | `path('', include('resumes.urls_v2'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:50` | `path('', include('community.urls_v2'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:51` | `path('', include('core.urls_v2'))` |
| `ai_interview_backend/ai_interview_backend/urls.py:54` | `path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema')` |
| `ai_interview_backend/ai_interview_backend/urls.py:56` | `path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui')` |
| `ai_interview_backend/ai_interview_backend/urls.py:58` | `path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc')` |
| `ai_interview_backend/blog/urls.py:5` | `router.register(r'posts', PostViewSet, basename='post')` |
| `ai_interview_backend/blog/urls.py:6` | `router.register(r'categories', CategoryViewSet, basename='category')` |
| `ai_interview_backend/blog/urls.py:7` | `router.register(r'tags', TagViewSet, basename='tag')` |
| `ai_interview_backend/blog/urls.py:11` | `posts_router.register(r'comments', CommentViewSet, basename='post-comments')` |
| `ai_interview_backend/careers/urls.py:24` | `router.register('career-facts', CareerFactViewSet, basename='career-fact')` |
| `ai_interview_backend/careers/urls.py:25` | `router.register('job-targets', JobTargetViewSet, basename='job-target')` |
| `ai_interview_backend/careers/urls.py:26` | `router.register('applications', JobApplicationViewSet, basename='job-application')` |
| `ai_interview_backend/careers/urls.py:27` | `router.register('learning-tasks', LearningTaskViewSet, basename='learning-task')` |
| `ai_interview_backend/careers/urls.py:28` | `router.register('career/timeline', CareerTimelineViewSet, basename='career-timeline')` |
| `ai_interview_backend/careers/urls.py:29` | `router.register('career/ability-snapshots', AbilitySnapshotViewSet, basename='ability-snapshot')` |
| `ai_interview_backend/careers/urls.py:30` | `router.register('career/weekly-reports', WeeklyCareerReportViewSet, basename='weekly-career-report')` |
| `ai_interview_backend/careers/urls.py:31` | `router.register('match-analyses', JobMatchAnalysisViewSet, basename='match-analysis')` |
| `ai_interview_backend/careers/urls.py:32` | `router.register('learning-plans', LearningPlanViewSet, basename='learning-plan')` |
| `ai_interview_backend/careers/urls.py:33` | `router.register('companies', PublicCompanyViewSet, basename='company')` |
| `ai_interview_backend/careers/urls.py:34` | `router.register('jobs', PublicJobPostingViewSet, basename='job-posting')` |
| `ai_interview_backend/careers/urls.py:35` | `router.register('employer/companies', EmployerCompanyViewSet, basename='employer-company')` |
| `ai_interview_backend/careers/urls.py:36` | `router.register('employer/jobs', EmployerJobPostingViewSet, basename='employer-job')` |
| `ai_interview_backend/careers/urls.py:39` | `path('career/profile/', CareerProfileView.as_view(), name='career-profile')` |
| `ai_interview_backend/careers/urls.py:40` | `path('career-dashboard/', CareerDashboardView.as_view(), name='career-dashboard')` |
| `ai_interview_backend/careers/urls.py:41` | `path('', include(router.urls))` |
| `ai_interview_backend/chat/urls.py:8` | `router.register(r'conversations', ConversationViewSet, basename='conversation')` |
| `ai_interview_backend/chat/urls.py:9` | `router.register(r'chat/blocks', UserBlockViewSet, basename='chat-block')` |
| `ai_interview_backend/chat/urls.py:12` | `conversations_router.register(r'messages', MessageViewSet, basename='conversation-messages')` |
| `ai_interview_backend/chat/urls.py:15` | `path('conversations/start_with/<int:user_id>/', StartConversationView.as_view(), name='start-conversation')` |
| `ai_interview_backend/chat/urls.py:16` | `path('chat/attachments/', AttachmentUploadView.as_view(), name='chat-attachment-upload')` |
| `ai_interview_backend/community/urls.py:14` | `path('community/me/', CommunityMeView.as_view(), name='community-me')` |
| `ai_interview_backend/community/urls.py:15` | `path('community/discourse/connect/', DiscourseConnectView.as_view(), name='discourse-connect')` |
| `ai_interview_backend/community/urls.py:16` | `path('community/discourse/webhook/', DiscourseWebhookView.as_view(), name='discourse-webhook')` |
| `ai_interview_backend/community/urls.py:17` | `path('community/search/', PublicSearchView.as_view(), name='community-search')` |
| `ai_interview_backend/community/urls.py:18` | `path('community/feed/', CommunityFeedView.as_view(), name='community-feed')` |
| `ai_interview_backend/community/urls.py:19` | `path('community/index-status/', CommunityIndexStatusView.as_view(), name='community-index-status')` |
| `ai_interview_backend/core/urls.py:8` | `path('ws-tickets/', WebSocketTicketView.as_view(), name='websocket-ticket')` |
| `ai_interview_backend/core/urls.py:9` | `path('tasks/', AsyncOperationListView.as_view(), name='async-operation-list')` |
| `ai_interview_backend/core/urls.py:10` | `path('tasks/<uuid:pk>/', AsyncOperationDetailView.as_view(), name='async-operation-detail')` |
| `ai_interview_backend/core/urls.py:11` | `path('tasks/<uuid:pk>/retry/', AsyncOperationRetryView.as_view(), name='async-operation-retry')` |
| `ai_interview_backend/core/urls.py:12` | `path('tasks/<uuid:pk>/cancel/', AsyncOperationCancelView.as_view(), name='async-operation-cancel')` |
| `ai_interview_backend/interactions/urls.py:5` | `path('posts/<int:pk>/like/', LikeToggleView.as_view(), name='post-like-toggle')` |
| `ai_interview_backend/interactions/urls.py:6` | `path('posts/<int:pk>/bookmark/', BookmarkToggleView.as_view(), name='post-bookmark-toggle')` |
| `ai_interview_backend/interactions/urls.py:7` | `path('users/<int:pk>/follow/', FollowToggleView.as_view(), name='user-follow-toggle')` |
| `ai_interview_backend/interviews/urls.py:16` | `router.register(r'interviews', InterviewSessionViewSet, basename='interview')` |
| `ai_interview_backend/interviews/urls.py:17` | `router.register(r'interview-templates', InterviewTemplateViewSet, basename='interview-template')` |
| `ai_interview_backend/interviews/urls.py:18` | `router.register(r'interview-rubrics', InterviewRubricViewSet, basename='interview-rubric')` |
| `ai_interview_backend/interviews/urls.py:19` | `router.register(r'interview-calibration-cases', InterviewCalibrationCaseViewSet, basename='interview-calibration-case')` |
| `ai_interview_backend/interviews/urls.py:20` | `router.register(r'evaluation-datasets', EvaluationDatasetViewSet, basename='evaluation-dataset')` |
| `ai_interview_backend/interviews/urls.py:21` | `router.register(r'evaluation-runs', EvaluationRunViewSet, basename='evaluation-run')` |
| `ai_interview_backend/interviews/urls.py:24` | `path('', include(router.urls))` |
| `ai_interview_backend/interviews/urls.py:26` | `path('polish-description/', PolishDescriptionView.as_view(), name='polish-description')` |
| `ai_interview_backend/interviews/urls.py:28` | `path('analyze-resume/', ResumeAnalysisView.as_view(), name='analyze-resume')` |
| `ai_interview_backend/knowledge/urls.py:7` | `router.register(r'knowledge/documents', KnowledgeDocumentViewSet, basename='knowledge-document')` |
| `ai_interview_backend/knowledge/urls.py:8` | `router.register(r'knowledge/import-batches', KnowledgeImportBatchViewSet, basename='knowledge-import-batch')` |
| `ai_interview_backend/knowledge/urls.py:11` | `path('knowledge/search/debug/', KnowledgeSearchDebugView.as_view(), name='knowledge-search-debug')` |
| `ai_interview_backend/knowledge/urls.py:12` | `path('', include(router.urls))` |
| `ai_interview_backend/notifications/urls.py:5` | `router.register(r'notifications', NotificationViewSet, basename='notification')` |
| `ai_interview_backend/reports/urls.py:9` | `router.register(r'analysis-reports', ResumeAnalysisReportViewSet, basename='analysis-report')` |
| `ai_interview_backend/reports/urls.py:12` | `path('', include(router.urls))` |
| `ai_interview_backend/resumes/urls.py:15` | `router.register(r'resumes', ResumeViewSet, basename='resume')` |
| `ai_interview_backend/resumes/urls.py:16` | `router.register(r'resume-imports', ResumeImportJobViewSet, basename='resume-import')` |
| `ai_interview_backend/resumes/urls.py:17` | `router.register(r'resume-suggestions', ResumeSuggestionViewSet, basename='resume-suggestion')` |
| `ai_interview_backend/resumes/urls.py:20` | `resumes_router.register(r'educations', EducationViewSet, basename='resume-educations')` |
| `ai_interview_backend/resumes/urls.py:21` | `resumes_router.register(r'work_experiences', WorkExperienceViewSet, basename='resume-work_experiences')` |
| `ai_interview_backend/resumes/urls.py:22` | `resumes_router.register(r'project_experiences', ProjectExperienceViewSet, basename='resume-project_experiences')` |
| `ai_interview_backend/resumes/urls.py:23` | `resumes_router.register(r'skills', SkillViewSet, basename='resume-skills')` |
| `ai_interview_backend/staff_admin/urls.py:49` | `path('auth/csrf/', StaffCsrfView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:50` | `path('auth/login/', StaffLoginView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:51` | `path('auth/security-setup/', StaffSecuritySetupView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:52` | `path('auth/activate/', StaffInvitationActivateView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:53` | `path('auth/invitations/<str:token>/', StaffInvitationDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:54` | `path('auth/register/', StaffInvitationRegisterView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:55` | `path('auth/session/', StaffSessionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:56` | `path('auth/logout/', StaffLogoutView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:57` | `path('dashboard/summary/', AdminDashboardView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:58` | `path('staff/', StaffAccountListCreateView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:59` | `path('staff-invitations/', StaffAccountListCreateView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:60` | `path('staff/<uuid:account_id>/', StaffAccountDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:61` | `path('staff/<uuid:account_id>/<str:action>/', StaffAccountActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:62` | `path('staff-invitations/<uuid:invitation_id>/<str:action>/', StaffInvitationActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:63` | `path('staff/roles/', StaffRoleListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:64` | `path('knowledge-reviews/', KnowledgeReviewListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:65` | `path('knowledge-reviews/<uuid:document_id>/', KnowledgeReviewAdminDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:66` | `path('knowledge-reviews/<uuid:document_id>/<str:decision>/', KnowledgeReviewDecisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:67` | `path('knowledge-documents/<uuid:document_id>/<str:action>/', KnowledgeDocumentAdminActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:68` | `path('knowledge-chunk-drafts/<uuid:chunk_id>/', KnowledgeChunkDraftAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:69` | `path('knowledge-chunk-drafts/<uuid:chunk_id>/<str:action>/', KnowledgeChunkDraftActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:70` | `path('interviews/', InterviewSessionAdminListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:71` | `path('interviews/<uuid:session_id>/', InterviewSessionAdminDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:72` | `path('interviews/<uuid:session_id>/<str:action>/', InterviewSessionAdminActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:73` | `path('agent-runs/', AgentRunListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:74` | `path('agent-runs/<uuid:run_id>/', AgentRunAdminDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:75` | `path('interview-config/<str:resource>/', InterviewConfigAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:76` | `path('agent-config/profiles/', AgentConfigProfileView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:77` | `path('agent-config/profiles/<uuid:profile_id>/revisions/', AgentConfigProfileRevisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:78` | `path('agent-config/revisions/<uuid:revision_id>/', AgentConfigRevisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:79` | `path('agent-config/revisions/<uuid:revision_id>/resolved-preview/', AgentConfigResolvedPreviewView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:80` | `path('agent-config/revisions/<uuid:revision_id>/<str:action>/', AgentConfigRevisionActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:81` | `path('agent-config/prompts/<path:task_key>/preview/', AgentPromptPreviewView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:82` | `path('agent-config/experiments/retrieval/', AgentConfigExperimentView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:83` | `path('agent-config/evaluation-datasets/', AgentConfigEvaluationDatasetView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:84` | `path('knowledge-bases/', KnowledgeBaseView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:85` | `path('knowledge-bases/revisions/<uuid:revision_id>/', KnowledgeBaseRevisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:86` | `path('retrieval-profiles/', RetrievalProfileView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:87` | `path('retrieval-profiles/revisions/<uuid:revision_id>/<str:action>/', RetrievalProfileActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:88` | `path('model-gateway/summary/', ModelGatewaySummaryView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:89` | `path('model-gateway/<str:resource>/', GatewayResourceAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:90` | `path('model-gateway/<str:resource>/<int:object_id>/', GatewayResourceAdminDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:91` | `path('tasks/', AdminTaskListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:92` | `path('tasks/<uuid:operation_id>/<str:action>/', AdminTaskActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:93` | `path('system/readiness/', AdminSystemHealthView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:94` | `path('system/resilience/', ResilienceMetricsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:95` | `path('candidates/', CandidateAccountListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:96` | `path('candidates/<int:candidate_id>/', CandidateAccountDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:97` | `path('candidates/<int:candidate_id>/break-glass/', CandidateBreakGlassView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:98` | `path('candidates/<int:candidate_id>/<str:action>/', CandidateAccountActionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:99` | `path('privacy-requests/', PrivacyRequestListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:100` | `path('privacy-requests/<int:request_id>/<str:decision>/', PrivacyRequestDecisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:101` | `path('moderation/reports/', ModerationReportListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:102` | `path('moderation/reports/<int:report_id>/<str:decision>/', ModerationReportDecisionView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:103` | `path('content/operations/', ContentOperationsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:104` | `path('notifications/operations/', NotificationOperationsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:105` | `path('analytics/', AnalyticsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:106` | `path('feature-flags/', FeatureFlagAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:107` | `path('feature-flags/<int:flag_id>/', FeatureFlagAdminDetailView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:108` | `path('maintenance-notices/', MaintenanceNoticeAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:109` | `path('audit-logs/', AdminAuditListView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:110` | `path('career-config/', CareerConfigAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:111` | `path('resume-config/', ResumeConfigAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:112` | `path('companies/', CompanyReviewAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:113` | `path('companies/<uuid:company_id>/<str:decision>/', CompanyReviewAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:114` | `path('jobs/', JobReviewAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:115` | `path('jobs/<uuid:job_id>/<str:decision>/', JobReviewAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:116` | `path('community/moderation/', CommunityModerationAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:117` | `path('community/moderation/<uuid:case_id>/<str:decision>/', CommunityModerationAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:118` | `path('operations/events/', PlatformEventsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:119` | `path('operations/events/<uuid:event_id>/replay/', PlatformEventsAdminView.as_view())` |
| `ai_interview_backend/staff_admin/urls.py:120` | `path('reliability/', ReliabilityAdminView.as_view())` |
| `ai_interview_backend/system/urls.py:21` | `router.register('gateway/credentials', ProviderCredentialViewSet, basename='gateway-credential')` |
| `ai_interview_backend/system/urls.py:22` | `router.register('gateway/deployments', ModelDeploymentViewSet, basename='gateway-deployment')` |
| `ai_interview_backend/system/urls.py:23` | `router.register('gateway/aliases', ModelAliasViewSet, basename='gateway-alias')` |
| `ai_interview_backend/system/urls.py:24` | `router.register('gateway/route-policies', RoutePolicyViewSet, basename='gateway-route-policy')` |
| `ai_interview_backend/system/urls.py:25` | `router.register('gateway/route-targets', RoutePolicyTargetViewSet, basename='gateway-route-target')` |
| `ai_interview_backend/system/urls.py:26` | `router.register('gateway/budgets', UsageBudgetViewSet, basename='gateway-budget')` |
| `ai_interview_backend/system/urls.py:27` | `router.register('gateway/requests', ModelRequestLedgerViewSet, basename='gateway-request')` |
| `ai_interview_backend/system/urls.py:30` | `path('', include(router.urls))` |
| `ai_interview_backend/system/urls.py:31` | `path('system/readiness/', SystemReadinessView.as_view(), name='system-readiness')` |
| `ai_interview_backend/system/urls.py:32` | `path('settings/ai/', AISettingRetrieveUpdateView.as_view(), name='ai-settings')` |
| `ai_interview_backend/system/urls.py:33` | `path('settings/ai/health/', AIModelGatewayHealthView.as_view(), name='ai-settings-health')` |
| `ai_interview_backend/system/urls.py:34` | `path('jobs-by-industry/', IndustryWithJobsListView.as_view(), name='jobs-by-industry-list')` |
| `ai_interview_backend/system/urls.py:35` | `path('ai-models/', AIModelListView.as_view(), name='ai-model-list'), # 新增` |
| `ai_interview_backend/users/urls.py:30` | `path('csrf/', CsrfTokenView.as_view(), name='auth-csrf')` |
| `ai_interview_backend/users/urls.py:31` | `path('session/', BrowserSessionView.as_view(), name='browser-session')` |
| `ai_interview_backend/users/urls.py:33` | `path('register/', UserRegisterView.as_view(), name='user-register')` |
| `ai_interview_backend/users/urls.py:34` | `path('send-code/', SendCodeView.as_view(), name='send-code')` |
| `ai_interview_backend/users/urls.py:35` | `path('upload-avatar/', AvatarUploadView.as_view(), name='upload-avatar')` |
| `ai_interview_backend/users/urls.py:36` | `path('profile/', UserProfileView.as_view(), name='user-profile')` |
| `ai_interview_backend/users/urls.py:37` | `path('onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete')` |
| `ai_interview_backend/users/urls.py:38` | `path('password/change/', PasswordChangeView.as_view(), name='password-change')` |
| `ai_interview_backend/users/urls.py:39` | `path('notification-preferences/', NotificationPreferenceView.as_view(), name='notification-preferences')` |
| `ai_interview_backend/users/urls.py:40` | `path('sessions/', AuthSessionListView.as_view(), name='auth-sessions')` |
| `ai_interview_backend/users/urls.py:41` | `path('sessions/<uuid:session_id>/revoke/', AuthSessionRevokeView.as_view(), name='auth-session-revoke')` |
| `ai_interview_backend/users/urls.py:42` | `path('logout/', LogoutView.as_view(), name='logout')` |
| `ai_interview_backend/users/urls.py:43` | `path('logout-all/', LogoutView.as_view(), {'all_sessions': True}, name='logout-all')` |
| `ai_interview_backend/users/urls.py:44` | `path('privacy-requests/', PrivacyRequestView.as_view(), name='privacy-requests')` |
| `ai_interview_backend/users/urls.py:45` | `path('mfa/status/', MFAStatusView.as_view(), name='mfa-status')` |
| `ai_interview_backend/users/urls.py:46` | `path('mfa/setup/', MFASetupView.as_view(), name='mfa-setup')` |
| `ai_interview_backend/users/urls.py:47` | `path('mfa/verify/', MFAVerifyView.as_view(), name='mfa-verify')` |
| `ai_interview_backend/users/urls.py:48` | `path('mfa/disable/', MFADisableView.as_view(), name='mfa-disable')` |
| `ai_interview_backend/users/urls.py:51` | `path('oauth/github/start/', GitHubOAuthStartView.as_view(), name='github-oauth-start')` |
| `ai_interview_backend/users/urls.py:52` | `path('oauth/github/callback/', GitHubOAuthCallbackView.as_view(), name='github-oauth-callback')` |
| `ai_interview_backend/users/urls.py:53` | `path('oauth/github/link/confirm/', GitHubLinkConfirmView.as_view(), name='github-link-confirm')` |
| `ai_interview_backend/users/urls.py:54` | `path('github/', GitHubLogin.as_view(), name='github_login')` |
| `ai_interview_backend/users/urls.py:55` | `path('github/connect/', GitHubConnect.as_view(), name='github_connect')` |
| `ai_interview_backend/users/urls.py:58` | `path('social/disconnect/<int:account_id>/', SocialAccountDisconnectView.as_view(), name='social-disconnect')` |
| `ai_interview_backend/users/urls.py:61` | `path('registration/', include('dj_rest_auth.registration.urls'))` |
| `ai_interview_backend/video_uploads/urls.py:13` | `router.register(r'tasks', FileUploadTaskViewSet, basename='upload-task')` |
| `ai_interview_backend/video_uploads/urls.py:14` | `router.register(r'transcode-tasks', VideoTranscodeTaskViewSet, basename='transcode-task')` |
| `ai_interview_backend/video_uploads/urls.py:17` | `path('init/', InitUploadView.as_view(), name='init-upload')` |
| `ai_interview_backend/video_uploads/urls.py:18` | `path('chunk/', ChunkUploadView.as_view(), name='chunk-upload')` |
| `ai_interview_backend/video_uploads/urls.py:19` | `path('merge/', MergeChunksView.as_view(), name='merge-chunks')` |
| `ai_interview_backend/video_uploads/urls.py:20` | `path('progress/', UploadProgressView.as_view(), name='upload-progress')` |
| `ai_interview_backend/video_uploads/urls.py:21` | `path('', include(router.urls))` |

## 前端路由

| 应用路由文件 | path |
|---|---|
| `ai-interview-frontend/src/router/index.ts` | `/` |
| `ai-interview-frontend/src/router/index.ts` | `/about` |
| `ai-interview-frontend/src/router/index.ts` | `/onboarding` |
| `ai-interview-frontend/src/router/index.ts` | `/login` |
| `ai-interview-frontend/src/router/index.ts` | `/register` |
| `ai-interview-frontend/src/router/index.ts` | `/interview/:id?` |
| `ai-interview-frontend/src/router/index.ts` | `/oauth/callback` |
| `ai-interview-frontend/src/router/index.ts` | `/oaauth/callback` |
| `ai-interview-frontend/src/router/index.ts` | `/oauth/callback:query(.*)` |
| `ai-interview-frontend/src/router/index.ts` | `/dashboard` |
| `ai-interview-frontend/src/router/index.ts` | `career` |
| `ai-interview-frontend/src/router/index.ts` | `community` |
| `ai-interview-frontend/src/router/index.ts` | `interviews` |
| `ai-interview-frontend/src/router/index.ts` | `interview/:id?` |
| `ai-interview-frontend/src/router/index.ts` | `resumes` |
| `ai-interview-frontend/src/router/index.ts` | `resumes/:id` |
| `ai-interview-frontend/src/router/index.ts` | `knowledge` |
| `ai-interview-frontend/src/router/index.ts` | `interview-admin` |
| `ai-interview-frontend/src/router/index.ts` | `history` |
| `ai-interview-frontend/src/router/index.ts` | `report/:id` |
| `ai-interview-frontend/src/router/index.ts` | `tasks` |
| `ai-interview-frontend/src/router/index.ts` | `settings` |
| `ai-interview-frontend/src/router/index.ts` | `model-gateway` |
| `ai-interview-frontend/src/router/index.ts` | `profile` |
| `ai-interview-frontend/src/router/index.ts` | `resume/edit/:id` |
| `ai-interview-frontend/src/router/index.ts` | `resume/preview/:id` |
| `ai-interview-frontend/src/router/index.ts` | `analysis/:reportId` |
| `ai-interview-frontend/src/router/index.ts` | `ai-diagnosis` |
| `ai-interview-frontend/src/router/index.ts` | `generate-resume` |
| `ai-interview-frontend/src/router/index.ts` | `blog` |
| `ai-interview-frontend/src/router/index.ts` | `blog/:id` |
| `ai-interview-frontend/src/router/index.ts` | `blog/edit/:id?` |
| `ai-interview-frontend/src/router/index.ts` | `blog/category/:categorySlug` |
| `ai-interview-frontend/src/router/index.ts` | `blog/tag/:tagSlug` |
| `ai-interview-frontend/src/router/index.ts` | `my-posts` |
| `ai-interview-frontend/src/router/index.ts` | `chat` |
| `ai-interview-frontend/src/router/index.ts` | `chat/:userId` |
| `ai-interview-frontend/src/router/index.ts` | `/resume-shares/:token` |
| `ai-interview-admin/src/router.ts` | `/login` |
| `ai-interview-admin/src/router.ts` | `/security-setup` |
| `ai-interview-admin/src/router.ts` | `/register` |
| `ai-interview-admin/src/router.ts` | `/activate` |
| `ai-interview-admin/src/router.ts` | `/` |
| `ai-interview-admin/src/router.ts` | `candidates` |
| `ai-interview-admin/src/router.ts` | `interviews` |
| `ai-interview-admin/src/router.ts` | `interview-config` |
| `ai-interview-admin/src/router.ts` | `agent-config` |
| `ai-interview-admin/src/router.ts` | `knowledge` |
| `ai-interview-admin/src/router.ts` | `agent-runs` |
| `ai-interview-admin/src/router.ts` | `gateway` |
| `ai-interview-admin/src/router.ts` | `operations` |
| `ai-interview-admin/src/router.ts` | `moderation` |
| `ai-interview-admin/src/router.ts` | `staff` |
| `ai-interview-admin/src/router.ts` | `audit` |
| `ai-interview-admin/src/router.ts` | `governance` |
| `ai-interview-admin/src/router.ts` | `career-config` |
| `ai-interview-admin/src/router.ts` | `resume-config` |
| `ai-interview-admin/src/router.ts` | `companies` |
| `ai-interview-admin/src/router.ts` | `jobs` |
| `ai-interview-admin/src/router.ts` | `community` |
| `ai-interview-admin/src/router.ts` | `operations/events` |
| `ai-interview-admin/src/router.ts` | `reliability` |

## Celery 任务

| 文件 | 任务函数 |
|---|---|
| `ai_interview_backend/blog/tasks.py` | `record_daily_stats` |
| `ai_interview_backend/blog/tasks.py` | `generate_recommendations_for_post` |
| `ai_interview_backend/careers/tasks.py` | `run_job_match_analysis` |
| `ai_interview_backend/careers/tasks.py` | `generate_weekly_career_reports` |
| `ai_interview_backend/chat/tasks.py` | `publish_pending_chat_outbox` |
| `ai_interview_backend/community/tasks.py` | `rebuild_public_search_indexes` |
| `ai_interview_backend/community/tasks.py` | `moderate_community_content` |
| `ai_interview_backend/community/tasks.py` | `index_community_content` |
| `ai_interview_backend/core/tasks.py` | `consume_integration_event` |
| `ai_interview_backend/core/tasks.py` | `publish_integration_outbox` |
| `ai_interview_backend/core/tasks.py` | `execute_operation` |
| `ai_interview_backend/core/tasks.py` | `publish_operation_dispatch_outbox` |
| `ai_interview_backend/core/tasks.py` | `recover_stale_operations_task` |
| `ai_interview_backend/interviews/tasks.py` | `cleanup_stale_interviews` |
| `ai_interview_backend/interviews/tasks.py` | `run_evaluation_run` |
| `ai_interview_backend/interviews/tasks.py` | `run_composite_v4_turn` |
| `ai_interview_backend/interviews/tasks.py` | `run_interview_execution` |
| `ai_interview_backend/interviews/tasks.py` | `publish_pending_agent_dispatches` |
| `ai_interview_backend/interviews/tasks.py` | `recover_stale_agent_executions` |
| `ai_interview_backend/knowledge/tasks.py` | `mark_stale_knowledge_jobs` |
| `ai_interview_backend/knowledge/tasks.py` | `process_knowledge_import_file` |
| `ai_interview_backend/knowledge/tasks.py` | `reparse_knowledge_document` |
| `ai_interview_backend/knowledge/tasks.py` | `reindex_knowledge_document` |
| `ai_interview_backend/notifications/tasks.py` | `publish_notification_outbox` |
| `ai_interview_backend/notifications/tasks.py` | `create_notification_task` |
| `ai_interview_backend/resumes/tasks.py` | `mark_stale_resume_import_jobs` |
| `ai_interview_backend/resumes/tasks.py` | `process_resume_import_job` |
| `ai_interview_backend/resumes/tasks.py` | `render_resume_artifact` |
| `ai_interview_backend/resumes/tasks.py` | `review_resume_quality` |
| `ai_interview_backend/resumes/tasks.py` | `generate_resume_suggestion_task` |
| `ai_interview_backend/staff_admin/tasks.py` | `publish_staff_email_outbox` |
| `ai_interview_backend/video_uploads/tasks.py` | `merge_chunks_task` |
| `ai_interview_backend/video_uploads/tasks.py` | `start_transcode_after_merge` |
| `ai_interview_backend/video_uploads/tasks.py` | `transcode_video_task` |
| `ai_interview_backend/video_uploads/tasks.py` | `cleanup_temp_files` |

## Service、Agent 与配置入口

| 文件 | Classes | Functions |
|---|---|---|
| `ai_interview_backend/careers/services.py` | — | `stable_hash`, `record_timeline_event`, `save_posting_as_target`, `create_learning_plan` |
| `ai_interview_backend/community/services.py` | `CommunityIntegrationError` | `database_public_content`, `verify_signature`, `build_discourse_sso_response`, `search_public_content`, `inspect_and_redact`, `content_hash`, `create_revision`, `submit_content` |
| `ai_interview_backend/interviews/agent_runtime.py` | `AgentToolSpec`, `AgentToolExecution`, `AgentToolRegistry`, `AgentToolExecutor`, `AgentHookManager`, `AgentSlashCommandRegistry`, `ContextBudgetManager` | `user_can_manage_agent_system`, `normalize_prompt_version`, `build_default_tool_registry`, `build_default_slash_commands` |
| `ai_interview_backend/interviews/agent_v4/engine.py` | `CompositeV4InterviewAgentEngine` | — |
| `ai_interview_backend/interviews/configuration.py` | `AgentConfigurationError`, `ContextItem` | `stable_hash`, `_bounded_int`, `validate_context_policy`, `validate_retrieval_config`, `validate_ingestion_policy`, `_jinja_environment`, `validate_prompt_source`, `_sanitize_template_value`, `render_prompt_source`, `_serialize_prompt`, `_serialize_knowledge_bindings`, `_revision_snapshot`, `settings_fallback_agent_config`, `resolve_agent_config`, `resolve_agent_config_revision`, `get_prompt_config`, `render_registered_prompt`, `validate_prompt_output`, `_count_tokens`, `_context_item`, `assemble_generation_context`, `assemble_initial_generation_context`, `build_revision_hash`, `validate_agent_config_revision` |
| `ai_interview_backend/knowledge/services.py` | `RequiredRAGContextUnavailable` | `split_text`, `_normalize_terms`, `_tokenize`, `_keyword_terms`, `_estimate_tokens`, `_embed_text`, `_qdrant_client`, `_qdrant_vector_size`, `_qdrant_alias_target`, `_create_qdrant_physical_collection`, `_ensure_qdrant_collection`, `_switch_qdrant_alias`, `_upsert_qdrant_chunk`, `_meili_headers`, `_meili_base_url`, `_meili_index_name`, `_wait_for_meili_task`, `_ensure_meili_knowledge_index`, `_meili_chunk_document`, `_upsert_meili_chunks`, `rebuild_qdrant_collection`, `index_document`, `build_structured_chunk_specs`, `merge_parent_specs`, `recursive_split`, `semantic_merge_short_chunks`, `materialize_revision_drafts`, `create_document_revision`, `build_preview_parsed_content`, `build_chunk_preview`, `build_retrieval_query`, `build_multi_queries`, `_plan_registered_queries`, `_retrieval_scopes`, `_scope_allows_chunk`, `_tenant_document_filter`, `_tenant_document_allowed`, `_matches_document`, `_sql_fallback_search`, `_context_from_chunk`, `_mark_contexts_retrieved`, `_rerank_contexts`, `_expand_parent_contexts`, `_expand_adjacent_contexts`, `_truncate_text_to_token_budget`, `_candidate_filter_reason`, `explain_retrieval_trace`, `_qdrant_query_filter`, `_vector_search_ranking`, `_threaded_vector_search_ranking`, `_meili_filter_value`, `_meili_search_ranking`, `search_knowledge_context`, `keyword_search_rankings`, `bm25_score`, `rrf_fuse`, `format_rag_context_for_prompt` |
| `ai_interview_backend/notifications/services.py` | — | `enqueue_notification` |
| `ai_interview_backend/resumes/services.py` | — | `extract_text_from_file`, `extract_text_with_document_parser`, `extract_text_from_pdf`, `extract_text_from_docx`, `extract_text_from_text` |
| `ai_interview_backend/staff_admin/services.py` | — | `enqueue_staff_invitation_email` |
| `ai_interview_backend/users/services.py` | — | `generate_email_code`, `_email_digest`, `_code_hmac`, `email_code_key`, `verify_email_code`, `send_verification_code` |
| `ai_interview_backend/video_uploads/services.py` | `FFmpegService` | — |

## Compose 基础设施服务

| Compose 文件 | Services |
|---|---|
| `docker-compose.infra.yml` | `postgres`, `redis-cache`, `redis-coordination`, `redis-realtime`, `rabbitmq`, `qdrant`, `litellm`, `meilisearch`, `clamav` |

关系运行库为 PostgreSQL；Redis/RabbitMQ/Qdrant/Meilisearch 等职责与当前配置见卷二、卷五和卷六。Compose service 名存在不等于应用 readiness 已通过。

## 测试入口

- `ai_interview_backend/ai_interview_backend/test_settings.py`
- `ai_interview_backend/blog/tests.py`
- `ai_interview_backend/careers/tests.py`
- `ai_interview_backend/chat/tests.py`
- `ai_interview_backend/community/test_operation_integration.py`
- `ai_interview_backend/community/tests.py`
- `ai_interview_backend/core/test_correlation.py`
- `ai_interview_backend/core/test_database.py`
- `ai_interview_backend/core/test_operations.py`
- `ai_interview_backend/core/test_redis_resilience.py`
- `ai_interview_backend/core/tests.py`
- `ai_interview_backend/interactions/tests.py`
- `ai_interview_backend/interviews/test_agent_config.py`
- `ai_interview_backend/interviews/test_agent_v4.py`
- `ai_interview_backend/interviews/test_evaluation_operation.py`
- `ai_interview_backend/interviews/tests.py`
- `ai_interview_backend/knowledge/test_operation_integration.py`
- `ai_interview_backend/knowledge/test_rag_control_plane.py`
- `ai_interview_backend/knowledge/tests.py`
- `ai_interview_backend/notifications/tests.py`
- `ai_interview_backend/questions/tests.py`
- `ai_interview_backend/reports/tests.py`
- `ai_interview_backend/resumes/test_migrations.py`
- `ai_interview_backend/resumes/test_operations.py`
- `ai_interview_backend/resumes/tests.py`
- `ai_interview_backend/staff_admin/test_authoritative_operation_dispatch.py`
- `ai_interview_backend/staff_admin/test_idempotency_claims.py`
- `ai_interview_backend/staff_admin/test_platform_reliability.py`
- `ai_interview_backend/staff_admin/tests.py`
- `ai_interview_backend/system/test_gateway_reliability.py`
- `ai_interview_backend/system/test_reliability_runtime.py`
- `ai_interview_backend/system/tests.py`
- `ai_interview_backend/users/test_verification_redis.py`
- `ai_interview_backend/users/tests.py`
- `ai_interview_backend/video_uploads/test_operation_integration.py`
- `scripts/tests/test_build_project_facts.py`
- `scripts/tests/test_check_docs_sync.py`
- `scripts/tests/test_interview_book.py`
- `ai-interview-frontend/tests/e2e/critical-flows.spec.ts`
- `ai-interview-frontend/tests/e2e/documentation-screenshots.spec.ts`

## 使用规则

1. 任何正文引用类、函数、路由、模型或测试前先在本索引或当前代码中核对。
2. 本索引自动生成，不能代替对应卷的正文更新。
3. `--check` 比较当前仓库事实和已提交索引；基线引用最近的应用/基础设施 Commit，避免文档提交自引用。
4. 历史 migration 中出现而当前代码已删除的符号不列为当前实现。
