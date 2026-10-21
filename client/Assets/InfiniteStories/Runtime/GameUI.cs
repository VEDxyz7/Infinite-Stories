using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace InfiniteStories
{
    public sealed class GameUI : MonoBehaviour
    {
        Color ink = new Color(.035f,.065f,.1f,.97f);
        readonly Color gold = new Color(.94f,.72f,.37f), pale = new Color(.85f,.91f,.93f);
        RectTransform canvas, overlay, hud, dialogue, tools, nightClock;
        readonly List<Image> visitLights=new List<Image>();
        GameView confirmed; CityAudio audioCues; bool scannerEvidence=true;
        public string ActivePanelText { get; private set; } = "";
        public string ActivePanel { get; private set; } = "";
        Text status, location, objectives;
        Font font;
        public bool Blocking { get; private set; }
        public bool TitleVisible { get; private set; }
        public Action Resume, StartAuthored, StartCultural, Interact, Retry, Reload, SubmitTurn, Pause, ReturnTitle;
        public string ActionText => actionInput != null ? actionInput.text : "";
        InputField actionInput;
        readonly List<Interest> interests = new List<Interest>();
        public static readonly string[] SupportedCategories = { "artist", "movie", "brand", "videogame" };
        public Interest[] SelectedInterests => interests.ToArray();
        public bool CulturalAvailable { get; private set; }
        public EntityCandidate[] ConfirmationCandidates { get; private set; } = Array.Empty<EntityCandidate>();
        Button culturalStart;
        Action<int> confirmCandidate;
        public void SetCulturalAvailability(bool available)
        {
            CulturalAvailable = available;
            if (culturalStart != null) { culturalStart.interactable = available; culturalStart.GetComponentInChildren<Text>().text = available ? "Start a culture-shaped journey" : "Cultural journey · temporarily unavailable"; }
        }
        public void AddBrowserInterest(Interest interest)
        {
            if (!TitleVisible || interests.Count >= 5 || interest == null || Array.IndexOf(SupportedCategories,interest.category)<0 || string.IsNullOrWhiteSpace(interest.name) || interest.name.Length>120) return;
            interest.entity_id = null;
            interests.Add(interest); ShowTitle(PlayerPrefs.HasKey("is.sessionId"));
            Status("Interest added: " + interest.name);
        }
        public void ConfirmCandidate(int index) { if (index>=0 && index<ConfirmationCandidates.Length) confirmCandidate?.Invoke(index); }
        public void ShowEntityConfirmation(ErrorDetails details, Action resume)
        {
            if (details == null || details.candidates == null || details.interest_index<0 || details.interest_index>=interests.Count) return;
            ClearOverlay(); TitleVisible=true; Blocking=true; hud.gameObject.SetActive(false);
            ConfirmationCandidates=details.candidates;
            overlay=Panel(canvas,new Vector2(.16f,.13f),new Vector2(.84f,.94f),ink);
            Label(overlay,"WHICH CULTURAL SEED?",25,new Vector2(.06f,.86f),new Vector2(.94f,.98f),gold);
            Label(overlay,"Choose the intended entity. Your existing saved journey stays unchanged.",16,new Vector2(.06f,.76f),new Vector2(.94f,.86f),pale);
            confirmCandidate = index => {
                EntityCandidate candidate=ConfirmationCandidates[index];
                if (candidate.category != interests[details.interest_index].category) return;
                interests[details.interest_index].entity_id=candidate.entity_id;
                ConfirmationCandidates=Array.Empty<EntityCandidate>(); confirmCandidate=null;
                ShowTitle(PlayerPrefs.HasKey("is.sessionId")); resume();
            };
            for (int i=0;i<Math.Min(5,details.candidates.Length);i++) {
                int candidateIndex=i; var candidate=details.candidates[i]; float y=.63f-i*.115f;
                string label=candidate.name+(string.IsNullOrEmpty(candidate.disambiguation)?"":" · "+candidate.disambiguation);
                Button(overlay,label,new Vector2(.06f,y),new Vector2(.94f,y+.10f),()=>ConfirmCandidate(candidateIndex));
            }
            Button(overlay,"Back to interests",new Vector2(.06f,.02f),new Vector2(.94f,.11f),()=>ShowTitle(PlayerPrefs.HasKey("is.sessionId")));
        }
        public bool TextFocused => EventSystem.current != null && EventSystem.current.currentSelectedGameObject != null && EventSystem.current.currentSelectedGameObject.GetComponent<InputField>() != null;

        public void Initialize()
        {
            if (PlayerPrefs.GetInt("is.contrast", 0) == 1) ink = Color.black;
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            audioCues=gameObject.AddComponent<CityAudio>();audioCues.Initialize();
            var go = new GameObject("Interface", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvas = go.GetComponent<RectTransform>(); go.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = go.GetComponent<CanvasScaler>(); scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280,720); scaler.matchWidthOrHeight = .5f;
            go.transform.SetParent(transform);
            if (EventSystem.current == null) new GameObject("Events", typeof(EventSystem), typeof(StandaloneInputModule));
            hud = Panel(canvas, new Vector2(.02f,.80f), new Vector2(.50f,.98f), ink);
            location = Label(hud, "", 22, new Vector2(.04f,.65f), new Vector2(.96f,.96f), gold);
            objectives = Label(hud, "", 15, new Vector2(.04f,.02f), new Vector2(.96f,.62f), pale);
            tools=Panel(canvas,new Vector2(.60f,.90f),new Vector2(.98f,.98f),ink);
            Button(tools,"Scanner",new Vector2(.02f,.12f),new Vector2(.32f,.88f),ShowScanner);
            Button(tools,"Journal",new Vector2(.35f,.12f),new Vector2(.65f,.88f),ShowJournal);
            Button(tools,"Pause",new Vector2(.68f,.12f),new Vector2(.98f,.88f),ShowPause);
            nightClock=Panel(canvas,new Vector2(.02f,.735f),new Vector2(.50f,.79f),ink);
            Label(nightClock,"UNTIL DAWN",12,new Vector2(.025f,.15f),new Vector2(.24f,.9f),gold);
            for(int i=0;i<12;i++){float x=.26f+i*.060f;visitLights.Add(Panel(nightClock,new Vector2(x,.25f),new Vector2(x+.044f,.75f),pale).GetComponent<Image>());}
            var footer = Panel(canvas, new Vector2(.02f,.02f), new Vector2(.98f,.16f), ink);
            status = Label(footer, "WASD / arrows · E interact · Esc pause", 16, new Vector2(.02f,.52f), new Vector2(.98f,.98f), pale);
            actionInput = Input(footer, "Try a free-form action…", new Vector2(.02f,.05f), new Vector2(.7f,.48f));
            Button(footer, "Ask Game Master", new Vector2(.72f,.05f), new Vector2(.98f,.48f), () => SubmitTurn?.Invoke());
            ShowTitle(false);
        }
        public bool ReplayVerification { get; set; }
        public void Status(string message) { message=(ReplayVerification ? "LOCAL CAPTURE REPLAY · " : "")+message; status.text = message; BrowserAccessibility.Status(message); }
        void ClearOverlay()
        {
            if (overlay != null) { overlay.gameObject.SetActive(false); Destroy(overlay.gameObject); }
            overlay = null; Blocking = false; ActivePanel=""; ActivePanelText=""; if(!TitleVisible&&confirmed!=null)SetHudVisible(true);
        }
        public void ShowTitle(bool canResume)
        {
            ConfirmationCandidates=Array.Empty<EntityCandidate>(); confirmCandidate=null;
            ClearOverlay(); CloseDialogue(); TitleVisible = true; Blocking = true; hud.gameObject.SetActive(false); tools.gameObject.SetActive(false); nightClock.gameObject.SetActive(false);
            overlay = Panel(canvas, new Vector2(.18f,.14f), new Vector2(.82f,.94f), ink);
            Label(overlay, "INFINITE STORIES", 36, new Vector2(.08f,.85f), new Vector2(.96f,.98f), gold);
            Label(overlay, "THE LAST LIGHT\nA city of borrowed memories. One tram before dawn.", 20, new Vector2(.08f,.69f), new Vector2(.93f,.85f), pale);
            Label(overlay, "Choose your cultural interests (optional for the authored chapter)", 15, new Vector2(.08f,.62f), new Vector2(.94f,.69f), pale);
            var input = Input(overlay, "An artist, film, brand or video game", new Vector2(.08f,.54f), new Vector2(.65f,.61f));
            input.characterLimit = 120;
            // Cycle categories without creating transient dropdown templates.
            string[] categories = SupportedCategories; int selected = 0;
            Button cycle = null;
            cycle = Button(overlay, categories[selected], new Vector2(.67f,.54f), new Vector2(.92f,.61f), () => {
                selected = (selected+1)%categories.Length; cycle.GetComponentInChildren<Text>().text = categories[selected]; });
            Text selection = Label(overlay, string.Join(" · ", interests.ConvertAll(i => i.name)), 14, new Vector2(.08f,.38f), new Vector2(.92f,.46f), pale);
            Button(overlay, "Add interest", new Vector2(.08f,.46f), new Vector2(.43f,.53f), () => {
                if (interests.Count < 5 && !string.IsNullOrWhiteSpace(input.text))
                { interests.Add(new Interest { name = input.text.Trim(), category = categories[selected] }); input.text = ""; }
                selection.text = string.Join(" · ", interests.ConvertAll(i => i.name)); });
            Button(overlay, "Clear", new Vector2(.46f,.46f), new Vector2(.65f,.53f), () => { interests.Clear(); selection.text = ""; });
            Button(overlay, canResume ? "Resume saved journey" : "Check for a saved journey", new Vector2(.08f,.27f), new Vector2(.92f,.36f), () => Resume?.Invoke());
            var play = Button(overlay, "Play the original authored chapter", new Vector2(.08f,.16f), new Vector2(.92f,.25f), () => StartAuthored?.Invoke());
            culturalStart = Button(overlay, "Start a culture-shaped journey", new Vector2(.08f,.05f), new Vector2(.92f,.14f), () => StartCultural?.Invoke());
            EventSystem.current.SetSelectedGameObject(play.gameObject);
            SetCulturalAvailability(CulturalAvailable);
            Status("Choose up to five interests for a cultural journey, or play the original authored chapter. Your selection never implies a personality profile.");
        }
        public void ShowGame(GameView view)
        {
            int previous=confirmed?.state.flags?.Length ?? 0;
            confirmed=view;
            ClearOverlay(); TitleVisible = false; CloseDialogue(); hud.gameObject.SetActive(true);tools.gameObject.SetActive(true);nightClock.gameObject.SetActive(true);
            for(int i=0;i<visitLights.Count;i++)visitLights[i].color=i<view.state.visits ? new Color(.22f,.3f,.4f) : gold;
            if((view.state.flags?.Length ?? 0)>previous)audioCues.Discovery();
            location.text = NightArt.Venue(view.location.id) + " · " + view.state.visits + "/12";
            var lines = new List<string>();
            int completed=0; foreach(var item in view.objectives)if(item.completed)completed++;
            string localGoal=view.location.id=="quay"?"map":view.location.id=="market"?"rhythm":view.location.id=="archive"?"chronicle":"beacon";
            Objective next=Array.Find(view.objectives,o=>!o.completed&&o.id==localGoal) ?? Array.Find(view.objectives,o=>!o.completed);
            lines.Add(next!=null ? "NEXT · "+next.label : "Every memory is secured.");
            lines.Add(completed+" / "+view.objectives.Length+" complete · Open Journal for all objectives");
            objectives.text = string.Join("\n", lines);
            if (!string.IsNullOrEmpty(view.narrative)) Status((view.narrative_source == "game_master_no_state_change" ? "Game Master reflection (no game changes): " : "") + view.narrative);
        }
        public void ShowDialogue(GameView view, WorldObject obj, Action<Command> act)
        {
            CloseDialogue(); Blocking = true; ActivePanel="dialogue"; ActivePanelText=obj.text; SetHudVisible(false); audioCues.Open();
            dialogue = Panel(canvas, new Vector2(.5f,.19f), new Vector2(.98f,.76f), ink);
            if(obj.kind=="npc" || obj.kind=="gate") {
                var portrait=Panel(dialogue,new Vector2(.05f,.81f),new Vector2(.17f,.97f),Color.white).GetComponent<Image>();
                portrait.sprite=NightArt.Character(obj.kind=="gate"?5:view.location.id=="market"?2:view.location.id=="archive"?3:1,1,0); portrait.preserveAspect=true;
            }
            Label(dialogue, obj.name, 23, new Vector2(.20f,.81f), new Vector2(.95f,.97f), gold);
            Label(dialogue, obj.text, 19, new Vector2(.05f,.51f), new Vector2(.95f,.81f), pale);
            float y = .38f;
            if (obj.kind == "portal")
            { Button(dialogue, "Travel", new Vector2(.05f,y), new Vector2(.95f,y+.09f), () => act(new Command { kind="travel", target=obj.id })); y -= .11f; }
            WorldObject nearby = Array.Find(view.nearby, o => o.id == obj.id);
            foreach (var option in nearby?.choices ?? Array.Empty<StoryChoice>())
            {
                StoryChoice choice = option;
                Button(dialogue, choice.label, new Vector2(.05f,y), new Vector2(.95f,y+.09f), () => act(new Command { kind="choose", target=obj.id, choice=choice.id })); y -= .11f;
            }
            Button(dialogue, "Return to the street", new Vector2(.05f,.03f), new Vector2(.95f,.12f), CloseDialogue);
        }
        public void CloseDialogue()
        { if (dialogue != null) { dialogue.gameObject.SetActive(false); Destroy(dialogue.gameObject); } dialogue = null; Blocking = overlay != null; if(!Blocking){ActivePanel="";ActivePanelText="";if(!TitleVisible&&confirmed!=null)SetHudVisible(true);} }
        public void ShowPause()
        {
            ClearOverlay(); CloseDialogue(); Blocking = true;
            overlay = Panel(canvas, new Vector2(.32f,.24f), new Vector2(.68f,.84f), ink);
            ActivePanel="pause";SetHudVisible(false);
            Label(overlay, "A MOMENT OF QUIET", 25, new Vector2(.08f,.8f), new Vector2(.92f,.95f), gold);
            Button(overlay, "Return to the city", new Vector2(.08f,.64f), new Vector2(.92f,.75f), ClearOverlay);
            Button(overlay, "Retry pending request", new Vector2(.08f,.49f), new Vector2(.92f,.60f), () => Retry?.Invoke());
            Button(overlay, "Reload confirmed save", new Vector2(.08f,.34f), new Vector2(.92f,.45f), () => Reload?.Invoke());
            Button(overlay,"Sound",new Vector2(.56f,.19f),new Vector2(.92f,.30f),()=>{PlayerPrefs.SetInt("is.muted",PlayerPrefs.GetInt("is.muted",0)==0?1:0);PlayerPrefs.Save();Status(PlayerPrefs.GetInt("is.muted",0)==1?"Sound muted.":"Sound enabled.");});
            bool highContrast = PlayerPrefs.GetInt("is.contrast", 0) == 1;
            Button(overlay, "High contrast", new Vector2(.08f,.19f), new Vector2(.54f,.30f), () => {
                highContrast = !highContrast; PlayerPrefs.SetInt("is.contrast", highContrast ? 1 : 0); PlayerPrefs.Save();
                ink = highContrast ? Color.black : new Color(.035f,.065f,.1f,.97f);
                overlay.GetComponent<Image>().color = ink; });
            Button(overlay, "Save & return to title", new Vector2(.08f,.04f), new Vector2(.92f,.15f), () => ReturnTitle?.Invoke());
        }
        public void ShowEnding(GameView view)
        {
            ClearOverlay(); CloseDialogue(); Blocking = true;SetHudVisible(false);ActivePanel="ending";
            overlay = Panel(canvas, new Vector2(.22f,.2f), new Vector2(.78f,.88f), ink);
            Label(overlay, view.state.ending == "keeper" ? "THE KEEPER OF LIGHT" : view.state.ending == "dawn" ? "ANOTHER NIGHT" : "STORIES CARRIED FORWARD", 29, new Vector2(.08f,.79f), new Vector2(.92f,.94f), gold);
            Label(overlay, view.state.history[view.state.history.Length-1], 22, new Vector2(.08f,.52f), new Vector2(.92f,.79f), pale);
            string card="TASTE CARD · YOUR FICTIONAL JOURNEY\n"+StoryTokens(view.state.flags)+"\n";
            var savedLinks=view.state.cultural_context?.links;
            if(savedLinks!=null && savedLinks.Length>0) {
                var link=savedLinks[0];var result=Array.Find(link.recommendations,e=>e.entity_id==link.selected_id);
                if(result!=null) card+="Saved Qloo connection: "+link.seed.name+" -> "+result.name+"\n";
                if(savedLinks.Length>1)card+=(savedLinks.Length-1)+" more saved cultural discoveries\n";
            }else card+="Original authored chapter\n";
            card+=view.state.visits+" visits · No individual profile or taste score inferred.";
            Label(overlay,card,17,new Vector2(.08f,.15f),new Vector2(.92f,.50f),pale);
            if (view.state.cultural_context?.links != null) {
                var discoveries = new List<string>();
                foreach (var link in view.state.cultural_context.links) {
                    var target=Array.Find(link.recommendations,e=>e.entity_id==link.selected_id);
                    if (target!=null) discoveries.Add(link.seed.name+" → "+target.name);
                }
                Status("Qloo discoveries: "+string.Join(" · ",discoveries)+". Story settings are original interpretations.");
            }
            Button(overlay, "Return to title", new Vector2(.08f,.03f), new Vector2(.92f,.13f), () => ReturnTitle?.Invoke());
        }
        public static string StoryTokens(string[] flags)
        {
            var labels=new List<string>();
            foreach(var flag in flags ?? Array.Empty<string>()) {
                switch(flag) {
                    case "map":labels.Add("Way home");break;
                    case "rhythm":labels.Add("City rhythm");break;
                    case "chronicle":labels.Add("Chronicle");break;
                    case "beacon":labels.Add("Gate opened");break;
                    case "guarding":labels.Add("Letters protected");break;
                    case "sharing":labels.Add("Stories shared");break;
                    case "kindness":labels.Add("Lantern relit");break;
                    default:labels.Add(flag.StartsWith("culture_",StringComparison.Ordinal)?"Cultural memory":flag.Replace('_',' '));break;
                }
            }
            return labels.Count==0 ? "No story tokens collected yet." : string.Join(" · ",labels);
        }
        public void ShowScanner()
        {
            if(confirmed==null || TitleVisible)return;
            OpenNotebook("CULTURAL SCANNER","scanner");
            string body=EvidenceText(confirmed,ReplayVerification,scannerEvidence);
            ScrollBody(overlay,body);
            Button(overlay,scannerEvidence ? "Compare: Qloo off" : "Return to Qloo evidence",new Vector2(.05f,.12f),new Vector2(.64f,.20f),ToggleScannerComparison);
            Label(overlay,"Read-only · no new provider requests",13,new Vector2(.05f,.04f),new Vector2(.70f,.10f),pale);
        }
        public void ToggleScannerComparison(){if(ActivePanel=="scanner"){scannerEvidence=!scannerEvidence;ShowScanner();}}
        // Pure presentation of server-confirmed data. No inference or synthetic provider facts.
        public static string EvidenceText(GameView view,bool replay,bool evidence=true)
        {
            if(!evidence)return "QLOO OFF · AUTHORED CONTROL\nInvented setting, not cultural evidence.\n\nA quiet night city. Three residents offer a way home, a rhythm and a promise.\n\nThis comparison changes only this panel. Your real saved cultural context, quest and progress remain unchanged.";
            var lines=new List<string>{replay?"LOCAL CAPTURE REPLAY · historical Qloo responses, no live calls":"SAVED QLOO EVIDENCE · no new requests", "Recommendations express aggregate cultural affinity, not facts about your personality or a collaboration.",""};
            var links=view?.state?.cultural_context?.links;
            if(links==null || links.Length==0) {lines.Add("Authored chapter · no Qloo cultural evidence is attached to this save.");return string.Join("\n",lines);}
            foreach(var link in links) {
                lines.Add("SEED · "+link.seed.name+" ["+link.seed.category+"]");lines.Add("Entity: "+link.seed.entity_id);
                foreach(var item in link.recommendations ?? Array.Empty<CulturalEntity>()) {
                    lines.Add("\n"+(item.entity_id==link.selected_id?"SELECTED · ":"RELATED · ")+item.name+" ["+item.category+"]"+(item.year>0?" · "+item.year:""));
                    lines.Add("Entity: "+item.entity_id);
                    if(!string.IsNullOrEmpty(item.description))lines.Add(item.description);
                    var tags=new List<string>();foreach(var tag in item.tags ?? Array.Empty<CulturalTag>())tags.Add(tag.name);if(tags.Count>0)lines.Add("Qloo tags: "+string.Join(" · ",tags));
                }
                lines.Add("\nOUR CREATIVE SETTING · "+link.setting+" (fictional interpretation; not a Qloo fact)");
                foreach(var proof in link.evidence ?? Array.Empty<CulturalEvidence>()) lines.Add("Provenance · "+proof.origin+proof.path+"\nRetrieved "+proof.retrieved_at+" · SHA256 "+proof.body_sha256);
                lines.Add("\n────────────────────────");
            }
            return string.Join("\n",lines);
        }
        public void ShowJournal()
        {
            if(confirmed==null || TitleVisible)return;
            OpenNotebook("NIGHT JOURNAL","journal");
            var lines=new List<string>{NightArt.Venue(confirmed.location.id),confirmed.location.name+" · visit "+confirmed.state.visits+" of 12","","CONFIRMED OBJECTIVES"};
            foreach(var goal in confirmed.objectives)lines.Add((goal.completed?"COMPLETE · ":"OPEN · ")+goal.label);
            lines.Add("\nINVENTORY / STORY TOKENS (fictional)");lines.Add(StoryTokens(confirmed.state.flags));
            lines.Add("\nCONFIRMED JOURNEY");foreach(var entry in confirmed.state.history ?? Array.Empty<string>())lines.Add("• "+entry+"\n");
            lines.Add("\nART & SOUND · Kenney (CC0) · original night composition by Infinite Stories.");ScrollBody(overlay,string.Join("\n",lines));
        }
        void OpenNotebook(string title,string kind)
        {
            ClearOverlay();CloseDialogue();Blocking=true;ActivePanel=kind;SetHudVisible(false);audioCues.Open();
            overlay=Panel(canvas,new Vector2(.16f,.18f),new Vector2(.84f,.88f),ink);
            Label(overlay,title,27,new Vector2(.05f,.87f),new Vector2(.92f,.98f),gold);
            Button(overlay,"Close",new Vector2(.76f,.035f),new Vector2(.95f,.12f),ClearOverlay);
        }
        void SetHudVisible(bool visible){hud.gameObject.SetActive(visible);tools.gameObject.SetActive(visible);nightClock.gameObject.SetActive(visible);}
        void ScrollBody(RectTransform parent,string body)
        {
            ActivePanelText=body;
            var viewport=Panel(parent,new Vector2(.05f,.23f),new Vector2(.95f,.85f),new Color(.025f,.05f,.08f));
            viewport.gameObject.AddComponent<RectMask2D>();
            var content=Label(viewport,body,17,Vector2.zero,Vector2.one,pale);
            var rect=content.rectTransform;rect.anchorMin=new Vector2(0,1);rect.anchorMax=Vector2.one;rect.pivot=new Vector2(.5f,1);rect.offsetMin=new Vector2(12,0);rect.offsetMax=new Vector2(-18,0);
            var fitter=content.gameObject.AddComponent<ContentSizeFitter>();fitter.verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            var scroll=viewport.gameObject.AddComponent<ScrollRect>();scroll.viewport=viewport;scroll.content=rect;scroll.horizontal=false;scroll.movementType=ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=28;
            // The viewport catches wheel/drag; text itself remains non-interactive.
        }
        RectTransform Panel(Transform parent, Vector2 min, Vector2 max, Color color)
        { var go = new GameObject("Panel", typeof(RectTransform), typeof(Image)); go.transform.SetParent(parent, false); var rect = go.GetComponent<RectTransform>(); Place(rect,min,max); go.GetComponent<Image>().color = color; return rect; }
        Text Label(Transform parent, string value, int size, Vector2 min, Vector2 max, Color color)
        { var go = new GameObject("Text", typeof(RectTransform), typeof(Text)); go.transform.SetParent(parent,false); var text = go.GetComponent<Text>(); Place(go.GetComponent<RectTransform>(),min,max); text.font=font; text.fontSize=size; text.color=color; text.text=value; text.supportRichText=false; text.horizontalOverflow=HorizontalWrapMode.Wrap; text.verticalOverflow=VerticalWrapMode.Truncate; text.raycastTarget=false; return text; }
        Button Button(Transform parent, string label, Vector2 min, Vector2 max, Action click)
        { var rect=Panel(parent,min,max,new Color(.12f,.23f,.29f)); var button=rect.gameObject.AddComponent<Button>(); button.targetGraphic=rect.GetComponent<Image>(); button.onClick.AddListener(() => { audioCues?.Click(); click(); }); var text=Label(rect,label,17,new Vector2(.04f,.08f),new Vector2(.96f,.92f),pale); text.alignment=TextAnchor.MiddleCenter; return button; }
        InputField Input(Transform parent, string placeholder, Vector2 min, Vector2 max)
        { var rect=Panel(parent,min,max,new Color(.09f,.14f,.2f)); var field=rect.gameObject.AddComponent<InputField>(); field.targetGraphic=rect.GetComponent<Image>(); field.characterLimit=1000; field.textComponent=Label(rect,"",17,new Vector2(.03f,.08f),new Vector2(.97f,.92f),pale); var hint=Label(rect,placeholder,16,new Vector2(.03f,.08f),new Vector2(.97f,.92f),new Color(.5f,.65f,.7f)); field.placeholder=hint; return field; }
        static void Place(RectTransform rect, Vector2 min, Vector2 max) { rect.anchorMin=min; rect.anchorMax=max; rect.offsetMin=Vector2.zero; rect.offsetMax=Vector2.zero; }
    }
}
