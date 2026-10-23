using System;
using System.Collections;
using UnityEngine;
using UnityEngine.EventSystems;

namespace InfiniteStories
{
    public sealed class GameClient : MonoBehaviour
    {
        public ClientSettings settings;
        ApiTransport api;
        TileWorld world;
        GameUI ui;
        GameView view;
        bool busy, thinking, turnQueued;
        float nextSave;
        const string PendingKey = "is.pendingRequest", SessionKey = "is.sessionId";
        public bool HasPending => PlayerPrefs.HasKey(PendingKey);

        void Start()
        {
            api=gameObject.AddComponent<ApiTransport>(); world=gameObject.AddComponent<TileWorld>(); ui=gameObject.AddComponent<GameUI>(); ui.Initialize();
            if (settings == null) settings=Resources.Load<ClientSettings>("ClientSettings");
            if (settings == null) settings=ScriptableObject.CreateInstance<ClientSettings>();
            bool release=!Debug.isDebugBuild;
#if INFINITE_STORIES_LOCAL_PREVIEW
            if(Uri.TryCreate(Application.absoluteURL,UriKind.Absolute,out var previewOrigin)&&previewOrigin.IsLoopback)release=false;
#endif
            try { settings.Validate(release); api.Origin=settings.apiOrigin; world.AvatarPrefab=settings.playerPrefab; }
            catch (ArgumentException error) { ui.Status(error.Message); enabled=false; return; }
            ui.RecordDiscovery=command=>{if(!busy&&!HasPending)StartCoroutine(Act(command));};
            ui.Resume=Resume; ui.Reload=ReloadConfirmed; ui.Retry=Retry;
            ui.StartAuthored=() => NewGame("authored"); ui.StartCultural=() => NewGame("cultural");
            ui.SubmitTurn=() => OnBrowserTurn(ui.ActionText);
            ui.ReturnTitle=() => { if (!busy) StartCoroutine(SaveAndTitle()); };
            ui.ShowTitle(PlayerPrefs.HasKey(SessionKey));
            StartCoroutine(LoadCapabilities());
            if (HasPending) ui.Status("An earlier request needs confirmation. Use Resume or Retry; your last confirmed save is safe.");
        }
        void Update()
        {
            ui.SetBusy(busy||turnQueued,thinking);
            BrowserAccessibility.Publish(view,ui.TitleVisible,ui.Blocking,busy||turnQueued,HasPending,ui.CulturalAvailable,ui.ConfirmationCandidates,ui.ActivePanel,ui.ActivePanelText,ui.StoryText,ui.DiagnosticEvidence);
            if (world.Player == null || ui.TitleVisible) return;
            world.Player.CanMove=!busy && !turnQueued && !HasPending && !ui.Blocking && !ui.TextFocused && string.IsNullOrEmpty(view.state.ending);
            if(Input.GetKeyDown(KeyCode.Escape)&&!busy){if(ui.TextFocused)EventSystem.current.SetSelectedGameObject(null);else if(ui.Blocking&&string.IsNullOrEmpty(view.state.ending))OnBrowserCommand("continue");else if(string.IsNullOrEmpty(view.state.ending))ui.ShowPause();}
            if(!busy&&!ui.TextFocused&&string.IsNullOrEmpty(view.state.ending)){if(Input.GetKeyDown(KeyCode.J))ui.ShowJournal();if(Input.GetKeyDown(KeyCode.C))ui.ShowScanner();}
            if (Input.GetKeyDown(KeyCode.E) && world.Player.CanMove) StartCoroutine(InteractNearest());
            if (Time.unscaledTime >= nextSave && world.Player.CanMove)
            { nextSave=Time.unscaledTime+.75f; if (Vector2.Distance(world.Player.Position,new Vector2(view.state.x,view.state.y)) > .05f) StartCoroutine(FlushPosition()); }
        }
        // Unity's documented SendMessage bridge, also usable by assistive browser controls.
        public void OnBrowserCommand(string command)
        {
            if (!enabled || ui==null || string.IsNullOrEmpty(command) || command.Length>200) return;
            if (command=="stop") { world.Player?.StopInput(); return; }
            if (command.StartsWith("confirm:",StringComparison.Ordinal) && !busy) { if (int.TryParse(command.Substring(8),out int candidate)) ui.ConfirmCandidate(candidate); return; }
            if (command=="cultural") { NewGame("cultural"); return; }
            if (command=="authored") { NewGame("authored"); return; }
            if (command=="resume") { Resume(); return; }
            if (command=="reload") { ReloadConfirmed(); return; }
            if (command=="retry") { Retry(); return; }
            if (busy || HasPending || view==null || ui.TitleVisible) return;
            if (command=="title") { StartCoroutine(SaveAndTitle()); return; }
            if (command=="continue") { ui.ShowGame(view); if (!string.IsNullOrEmpty(view.state.ending)) ui.ShowEnding(view); return; }
            if (command=="sound") { ui.ToggleSound();return; }
            if(command.StartsWith("scan:",StringComparison.Ordinal)){ui.SetScannerTool(command.Substring(5));return;}
            if (command=="story") { ui.ShowStory();return; }
            if (command=="compare") { ui.ToggleScannerComparison(); return; }
            if (command=="scanner") { world.Player.StopInput(); ui.ShowScanner(); return; }
            if (command=="journal") { world.Player.StopInput(); ui.ShowJournal(); return; }
            if (command=="pause") { world.Player.StopInput(); ui.ShowPause(); return; }
            if (ui.Blocking || !string.IsNullOrEmpty(view.state.ending)) return;
            // Moving focus to a DOM button does not clear uGUI's selection.
            // An explicit game command ends text entry before input is evaluated.
            if (ui.TextFocused) EventSystem.current.SetSelectedGameObject(null);
            if (command=="north") world.Player.Nudge(Vector2.up);
            else if (command=="south") world.Player.Nudge(Vector2.down);
            else if (command=="east") world.Player.Nudge(Vector2.right);
            else if (command=="west") world.Player.Nudge(Vector2.left);
            else if (command=="interact") StartCoroutine(InteractNearest());
            else
            {
                string[] parts=command.Split(':');
                if (parts.Length<2) return;
                var obj=Array.Find(view.nearby,o=>o.id==parts[1]);
                if (obj==null) return;
                if (parts[0]=="travel" && parts.Length==2 && obj.kind=="portal")
                    StartCoroutine(Act(new Command { kind="travel",target=obj.id }));
                else if (parts[0]=="choose" && parts.Length==3 && Array.Exists(obj.choices ?? Array.Empty<StoryChoice>(),c=>c.id==parts[2]))
                    StartCoroutine(Act(new Command { kind="choose",target=obj.id,choice=parts[2] }));
            }
        }
        IEnumerator LoadCapabilities()
        {
            yield return api.ReadCapabilities(value=>{ ui.ReplayVerification=value.verification_mode=="captured_response_replay";ui.SetModelMode(value.game_master_inference_mode); ui.SetCulturalAvailability(value.cultural_generation); if(ui.ReplayVerification)ui.Status("Qloo: saved-response replay, not live calls. Game Master: "+(value.game_master_inference_mode=="local_loopback"?"actual local model.":"unavailable on this service.")+""); },()=>ui.Status("The journey service is unavailable. You can retry or resume your last confirmed save."));
        }
        public void OnBrowserCulturalSeed(string json)
        {
            if (busy || HasPending || !ui.TitleVisible || string.IsNullOrEmpty(json) || json.Length>500) return;
            try { ui.AddBrowserInterest(JsonUtility.FromJson<Interest>(json)); } catch (ArgumentException) { ui.Status("That cultural interest could not be read."); }
        }
        void NewGame(string mode)
        {
            if (busy) return;
            if (HasPending) { ui.Status("Confirm the pending request before starting another journey."); return; }
            if (mode=="cultural" && !ui.CulturalAvailable) { ui.Status("Cultural journeys are temporarily unavailable. Your saved journey is safe."); return; }
            if (mode=="cultural" && ui.SelectedInterests.Length==0) { ui.Status("Add at least one artist, film, brand or game first."); return; }
            ui.Status(mode=="cultural" ? "Finding cultural connections and preparing your city…" : "Preparing the original chapter…");
            var request = new NewGameRequest { request_id=Guid.NewGuid().ToString(), mode=mode, interests=ui.SelectedInterests };
            StartCoroutine(Write("/v1/sessions",JsonUtility.ToJson(request)));
        }
        void Resume()
        {
            if (busy) return;
            if (HasPending) {
                var pending=ReadPending();
                if (IsCulturalCreation(pending)) StartCoroutine(RecoverCreation(pending));
                else Retry();
                return;
            }
            string id=PlayerPrefs.GetString(SessionKey,"");
            if (string.IsNullOrEmpty(id)) { ui.Status("No saved journey is linked to this browser. Start the authored chapter."); return; }
            StartCoroutine(Load(id));
        }
        PendingRequest ReadPending()
        {
            try { return JsonUtility.FromJson<PendingRequest>(PlayerPrefs.GetString(PendingKey)); }
            catch (ArgumentException) { return null; }
        }
        static bool IsCulturalCreation(PendingRequest pending)
        {
            if(pending==null||pending.path!="/v1/sessions"||pending.method!="POST")return false;
            try{return JsonUtility.FromJson<NewGameRequest>(pending.json)?.mode=="cultural";}
            catch(ArgumentException){return false;}
        }
        void ReloadConfirmed()
        {
            if(busy)return;
            var pending=ReadPending();
            if(IsCulturalCreation(pending)){StartCoroutine(RecoverCreation(pending));return;}
            string id=PlayerPrefs.GetString(SessionKey,"");
            if(string.IsNullOrEmpty(id)){ui.Status("No confirmed save is linked here. Use Resume to recover a pending creation, or start a new journey.");return;}
            // GET never replays a creation/provider operation. An uncertain action
            // remains pending until its original receipt is explicitly retried.
            StartCoroutine(Load(id));
        }
        IEnumerator RecoverCreation(PendingRequest pending)
        {
            busy=true;
            var request=new GenerationRecoveryRequest{creation=JsonUtility.FromJson<NewGameRequest>(pending.json),previous_session_id=PlayerPrefs.GetString(SessionKey,"")};
            ui.Status("Recovering your confirmed journey without repeating cultural requests…");
            yield return api.Send("/v1/sessions/recover","POST",JsonUtility.ToJson(request),incoming=>{
                PlayerPrefs.DeleteKey(PendingKey);PlayerPrefs.Save();Accept(incoming);
                if(incoming.notices!=null)foreach(string notice in incoming.notices)if(notice.StartsWith("The new journey was not confirmed",StringComparison.Ordinal))ui.Status(notice);
            },(error,uncertain)=>{
                // Only the server can confirm cancellation. Network/validation
                // failures retain the exact pending payload for safe recovery retry.
                if(error.code=="QLOO_GENERATION_INTERRUPTED"){
                    PlayerPrefs.DeleteKey(PendingKey);PlayerPrefs.Save();ui.ShowTitle(PlayerPrefs.HasKey(SessionKey));
                }
                ui.ServiceError(error.code,error.message,uncertain);
            });
            busy=false;
        }
        IEnumerator Load(string id)
        {
            busy=true;
            yield return api.Send("/v1/sessions/"+id,"GET",null,Accept,(error,_) => ui.Status(error.message));
            busy=false;
        }
        void Accept(GameView incoming)
        {
            if (view != null && incoming.session_id == view.session_id && incoming.revision < view.revision) return;
            if (view!=null && view.session_id!=incoming.session_id) world.Clear();
            view=incoming; PlayerPrefs.SetString(SessionKey,view.session_id); PlayerPrefs.Save();
            world.Show(view.location,view.state.x,view.state.y); world.ConfirmStory(view.state); ui.ShowGame(view);
            if (!string.IsNullOrEmpty(view.state.ending)) ui.ShowEnding(view);
        }
        IEnumerator Write(string path, string json)
        {
            busy=true;
            var pending=new PendingRequest { path=path, method="POST", json=json };
            PlayerPrefs.SetString(PendingKey,JsonUtility.ToJson(pending)); PlayerPrefs.Save();
            yield return Execute(pending);
            busy=false;
        }
        IEnumerator Execute(PendingRequest pending)
        {
            bool reloadStale = false;
            yield return api.Send(pending.path,pending.method,pending.json,incoming => {
                PlayerPrefs.DeleteKey(PendingKey); PlayerPrefs.Save(); Accept(incoming);
            }, (error, uncertain) => {
                // An explicit deterministic rejection is safe to discard. Timeouts
                // and 5xx retain the same request ID for an idempotent retry.
                bool generationPending=error.code=="QLOO_GENERATION_PENDING";
                if (generationPending) uncertain=true;
                if ((!uncertain && !generationPending) || (error.code!=null && error.code.StartsWith("QLOO_",StringComparison.Ordinal) && !generationPending) || error.code=="QLOO_NOT_VERIFIED" || error.code=="GAME_MASTER_UNAVAILABLE" ||
                    (error.code != null && error.code.StartsWith("MODEL_", StringComparison.Ordinal)))
                { PlayerPrefs.DeleteKey(PendingKey); PlayerPrefs.Save(); uncertain=false; }
                if (view != null && world.Player != null) world.Player.Restore(view.state.x,view.state.y);
                ui.ServiceError(error.code,error.message,uncertain);
                if (error.code=="QLOO_AMBIGUOUS") ui.ShowEntityConfirmation(error.details,()=>NewGame("cultural"));
                if (error.code=="STALE_REVISION") reloadStale=true;
            });
            if (reloadStale) yield return api.Send("/v1/sessions/"+PlayerPrefs.GetString(SessionKey),"GET",null,Accept,(error,_) => ui.Status(error.message));
        }
        void Retry()
        {
            if (busy) return;
            if (!HasPending) { ui.Status("There is no pending request."); return; }
            PendingRequest pending=ReadPending();
            if (pending == null || string.IsNullOrEmpty(pending.path)) { ui.Status("The local retry record is invalid; no request was sent."); return; }
            if(IsCulturalCreation(pending))StartCoroutine(RecoverCreation(pending));
            else StartCoroutine(RetryRoutine(pending));
        }
        IEnumerator RetryRoutine(PendingRequest pending) { busy=true; yield return Execute(pending); busy=false; }
        IEnumerator FlushPosition()
        {
            if (busy || HasPending || view == null || !string.IsNullOrEmpty(view.state.ending)) yield break;
            Vector2 point=world.Player.Position;
            if (Vector2.Distance(point,new Vector2(view.state.x,view.state.y)) < .05f) yield break;
            yield return Act(new Command { kind="position", x=point.x, y=point.y });
        }
        IEnumerator Act(Command command)
        {
            var request=new ActionRequest { request_id=Guid.NewGuid().ToString(), expected_revision=view.revision, command=command };
            yield return Write("/v1/sessions/"+view.session_id+"/actions",JsonUtility.ToJson(request));
        }
        IEnumerator InteractNearest()
        {
            yield return FlushPosition(); if (HasPending || busy || view==null) yield break;
            WorldObject nearest=null; float distance=2f;
            foreach (WorldObject obj in view.nearby)
            {
                float d=Vector2.Distance(world.Player.Position,new Vector2(obj.x,obj.y));
                if (d <= distance) { nearest=obj; distance=d; }
            }
            if (nearest==null) { ui.Status("Move closer to a resident, object or arch, then press E."); yield break; }
            // Opening a resident encounter is a confirmed backend action, not
            // a local-only dialogue panel. All input paths use this coroutine.
            if (nearest.kind=="npc" || nearest.kind=="gate")
            {
                yield return Act(new Command { kind="interact",target=nearest.id });
                if (busy || HasPending || view==null || !string.IsNullOrEmpty(view.state.ending)) yield break;
            }
            if (view.state.visit_rules=="conversation-v1" && (nearest.kind=="npc" || nearest.kind=="gate") && view.state.encounter_id!=nearest.id) yield break;
            world.Emphasize(nearest.id);
            ui.ShowDialogue(view,nearest,command => { if (!busy && !HasPending) StartCoroutine(Act(command)); });
        }
        public void OnBrowserTurn(string text){if(enabled&&!busy&&!turnQueued&&!HasPending&&view!=null&&!ui.TitleVisible&&(!ui.Blocking||ui.ActivePanel=="dialogue")&&string.IsNullOrEmpty(view.state.ending)&&!string.IsNullOrWhiteSpace(text)&&text.Length<=1000){if(ui.ActivePanel=="dialogue")ui.CloseDialogue();turnQueued=true;StartCoroutine(SaveThenTurn(text));}}
        IEnumerator SaveThenTurn(string text)
        {
            try {
                yield return FlushPosition(); if (busy || HasPending) yield break;
                var request=new TurnRequest { request_id=Guid.NewGuid().ToString(), expected_revision=view.revision, text=text };
                thinking=true;ui.Status("The Game Master is considering your action. Your confirmed progress is safe.");
                yield return Write("/v1/sessions/"+view.session_id+"/turns",JsonUtility.ToJson(request));
            } finally {thinking=false;turnQueued=false;}
        }
        IEnumerator SaveAndTitle()
        {
            yield return FlushPosition();
            if (busy || HasPending) { ui.Status("The last request needs confirmation before leaving the city."); yield break; }
            if (world.Player!=null) world.Player.CanMove=false;
            ui.ShowTitle(PlayerPrefs.HasKey(SessionKey));
        }
    }
}
