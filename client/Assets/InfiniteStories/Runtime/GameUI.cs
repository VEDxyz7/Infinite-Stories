using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace InfiniteStories
{
    public sealed class GameUI : MonoBehaviour
    {
        Color ink = new Color(.035f,.065f,.1f,1);
        readonly Color gold = new Color(.94f,.72f,.37f), pale = new Color(.85f,.91f,.93f);
        RectTransform canvas, overlay, hud, dialogue, tools, nightClock, footer,errorNotice;
        Button askButton; string endingCueSession;int scannerTool;string scannerQuery="";Text scannerBodyText;RectTransform tutorial;
        public Action<Command> RecordDiscovery;
        public string StoryText { get; private set; }=""; string modelMode="unavailable";
        public bool ModelAvailable => modelMode!="unavailable";
        public void SetModelMode(string mode){modelMode=string.IsNullOrEmpty(mode)?"unavailable":mode;}
        public void SetBusy(bool busy,bool thinking){if(askButton!=null){askButton.interactable=!busy&&(!Blocking||ActivePanel=="dialogue")&&!TitleVisible&&ModelAvailable&&string.IsNullOrEmpty(confirmed?.state.ending);askButton.GetComponentInChildren<Text>().text=thinking?"Listening to the city…":ModelAvailable?"Send action":"Game Master offline";}if(actionInput!=null)actionInput.interactable=!busy&&(!Blocking||ActivePanel=="dialogue")&&!TitleVisible&&ModelAvailable&&string.IsNullOrEmpty(confirmed?.state.ending);}
        readonly List<Image> visitLights=new List<Image>();
        GameView confirmed; CityAudio audioCues; bool scannerEvidence=true;
        public string ActivePanelText { get; private set; } = "";
        public string ActivePanel { get; private set; } = "";
        Text status, location, objectives, modeLabel,titleMode,dialogueFeedback;
        Font font;
        public Rect WorldViewport => TitleVisible ? new Rect(.60f,0,.40f,.915f) : ActivePanel=="dialogue" ? new Rect(0,.32f,1,.595f) : (ActivePanel=="scanner"||ActivePanel=="journal"||ActivePanel=="story"||ActivePanel=="pause") ? new Rect(0,0,.60f,.915f) : ActivePanel=="ending" ? new Rect(0,0,.57f,.915f) : new Rect(0,.18f,1,.735f);
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
            CulturalAvailable = available;if(titleMode!=null)titleMode.text=ReplayVerification?"REPLAY PREVIEW · saved cultural responses\n"+(ModelAvailable?"Local Game Master":"Game Master unavailable"):"Four cultural paths. Your choices shape the night.";
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
            if(Camera.main==null){var back=new GameObject("World Camera");back.tag="MainCamera";var camera=back.AddComponent<Camera>();camera.backgroundColor=ink;camera.clearFlags=CameraClearFlags.SolidColor;}
            var backdrop=new GameObject("Screen clear pass");backdrop.transform.SetParent(transform);var clear=backdrop.AddComponent<Camera>();clear.clearFlags=CameraClearFlags.SolidColor;clear.backgroundColor=ink;clear.cullingMask=0;clear.depth=-100;
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            audioCues=gameObject.AddComponent<CityAudio>();audioCues.Initialize();
            var go = new GameObject("Interface", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvas = go.GetComponent<RectTransform>(); go.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = go.GetComponent<CanvasScaler>(); scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280,720); scaler.matchWidthOrHeight = .5f;
            go.transform.SetParent(transform);
            if (EventSystem.current == null) new GameObject("Events", typeof(EventSystem), typeof(StandaloneInputModule));
            // One game-owned composition: header, playable world, narrative dock.
            hud = Panel(canvas,new Vector2(0,.915f),Vector2.one,ink);
            location=Label(hud,"",23,new Vector2(.025f,.48f),new Vector2(.40f,.94f),gold);
            objectives=Label(hud,"",15,new Vector2(.025f,.06f),new Vector2(.58f,.45f),pale);
            tools=Panel(canvas,new Vector2(.68f,.93f),new Vector2(.985f,.985f),ink);
            Button(tools,"Scanner",new Vector2(0,0),new Vector2(.31f,1),ShowScanner);
            Button(tools,"Journal",new Vector2(.34f,0),new Vector2(.65f,1),ShowJournal);
            Button(tools,"Menu",new Vector2(.68f,0),Vector2.one,ShowPause);
            nightClock=Panel(canvas,new Vector2(.44f,.962f),new Vector2(.65f,.99f),ink);
            for(int i=0;i<12;i++){float x=i*.083f;visitLights.Add(Panel(nightClock,new Vector2(x,.18f),new Vector2(x+.062f,.75f),gold).GetComponent<Image>());}
            modeLabel=Label(hud,"",12,new Vector2(.44f,.06f),new Vector2(.665f,.45f),new Color(.55f,.68f,.71f));modeLabel.alignment=TextAnchor.MiddleLeft;
            footer=Panel(canvas,Vector2.zero,new Vector2(1,.18f),ink);
            var storyLink=Label(footer,"STORY · click to read the full passage",12,new Vector2(.025f,.80f),new Vector2(.40f,.98f),gold);storyLink.raycastTarget=true;var storyButton=storyLink.gameObject.AddComponent<Button>();storyButton.targetGraphic=storyLink;storyButton.onClick.AddListener(ShowStory);
            Label(footer,"WASD / arrows · E interact · Esc menu",12,new Vector2(.62f,.80f),new Vector2(.975f,.98f),new Color(.55f,.68f,.71f));
            status=Label(footer,"Find Mara inside Side A.",17,new Vector2(.025f,.43f),new Vector2(.975f,.79f),pale);
            actionInput=Input(footer,"What do you say or do?",new Vector2(.025f,.08f),new Vector2(.80f,.37f));
            askButton=Button(footer,"Send action",new Vector2(.815f,.08f),new Vector2(.975f,.37f),()=>SubmitTurn?.Invoke());
            ShowTitle(false);
        }
        public bool ReplayVerification { get; set; }
        public void Status(string message) {
            if(string.IsNullOrWhiteSpace(message)||message=="Position saved.")return;
            BrowserAccessibility.Status((ReplayVerification?"LOCAL CAPTURE REPLAY · ":"")+message);
            if(TitleVisible&&(message.IndexOf("unavailable",StringComparison.OrdinalIgnoreCase)>=0||message.IndexOf("could not",StringComparison.OrdinalIgnoreCase)>=0))ShowErrorNotice(message);
            if(message.StartsWith("Qloo: saved-response")||message.StartsWith("Verification service"))return;
            string summary=message.Replace("Game Master reflection (no game changes): ","").Replace("Saved Qloo evidence (server-rendered): ","Saved cultural connection: ").Replace("→"," -> ");
            status.text=summary.Length>180?summary.Substring(0,177).TrimEnd()+"…":summary;
        }
        public void ServiceError(string code,string message,bool uncertain){
            BrowserAccessibility.Status(message);
            status.text=code=="QLOO_GENERATION_INTERRUPTED"?message:code!=null&&code.StartsWith("MODEL_",StringComparison.Ordinal)?"The storyteller is unavailable. Your progress is safe. Try again shortly.":code!=null&&code.StartsWith("QLOO_",StringComparison.Ordinal)?"Cultural discoveries could not be reached. Your saved journey is safe.":message;
            if(ActivePanel=="dialogue"&&dialogueFeedback!=null)dialogueFeedback.text=status.text;
            else if(ActivePanel=="scanner"&&scannerBodyText!=null){scannerBodyText.text+="\n"+status.text;ActivePanelText=scannerBodyText.text;}
            else if(TitleVisible)ShowErrorNotice(status.text);
            if(uncertain)status.text+=" Open Menu to retry or resume your confirmed save.";
        }
        void DismissErrorNotice(){if(errorNotice!=null)Destroy(errorNotice.gameObject);errorNotice=null;}
        void ShowErrorNotice(string message){DismissErrorNotice();errorNotice=Panel(canvas,new Vector2(.08f,.015f),new Vector2(.92f,.10f),ink);Label(errorNotice,message,17,new Vector2(.025f,.05f),new Vector2(.975f,.95f),gold);}
        void ClearOverlay()
        {
            if (overlay != null) { overlay.gameObject.SetActive(false); Destroy(overlay.gameObject); }
            overlay = null; Blocking = false; ActivePanel=""; ActivePanelText=""; if(!TitleVisible&&confirmed!=null)SetHudVisible(true);
        }
        public void ShowTitle(bool canResume)
        {
            DismissErrorNotice();if(tutorial!=null){Destroy(tutorial.gameObject);tutorial=null;}
            ConfirmationCandidates=Array.Empty<EntityCandidate>(); confirmCandidate=null;
            ClearOverlay(); CloseDialogue(); TitleVisible = true; Blocking = true; hud.gameObject.SetActive(false); tools.gameObject.SetActive(false); nightClock.gameObject.SetActive(false);
            SetFooter(false);
            overlay = Panel(canvas,new Vector2(.08f,.12f),new Vector2(.58f,.91f),ink);
            TitleVignette(overlay);
            Label(overlay, "INFINITE STORIES", 36, new Vector2(.08f,.85f), new Vector2(.96f,.98f), gold);
            Label(overlay, "THE LAST LIGHT\nThe city closes at dawn. Whose stories will you carry?", 20, new Vector2(.08f,.69f), new Vector2(.93f,.85f), pale);
            Label(overlay, "Bring a cultural memory into the night", 15, new Vector2(.08f,.62f), new Vector2(.94f,.69f), pale);
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
            Status("Four places. Three residents. Twelve visits before dawn.");
        }
        void TitleVignette(RectTransform parent)
        {
            var art=Panel(parent,new Vector2(1.08f,.04f),new Vector2(1.74f,.96f),Color.clear);
            Label(art,"ONE NIGHT.\nFOUR DOORS.",31,new Vector2(0,.76f),new Vector2(1,.98f),gold);
            Label(art,"A record sleeve. A final screening.\nA promise stitched into a coat.",17,new Vector2(0,.60f),new Vector2(1,.76f),pale);
            for(int y=0;y<7;y++)for(int x=0;x<12;x++){
                int tile=y==0?468:y==6?109:36;
                var image=Panel(art,new Vector2(x/12f,.19f+y*.05f),new Vector2((x+1)/12f,.19f+(y+1)*.05f),new Color(.3f,.4f,.57f)).GetComponent<Image>();image.sprite=NightArt.Tile(tile);
            }
            for(int i=0;i<4;i++){var image=Panel(art,new Vector2(.07f+i*.23f,.24f),new Vector2(.22f+i*.23f,.40f),Color.white).GetComponent<Image>();image.sprite=NightArt.Character(i==3?5:i+1,1,0);image.preserveAspect=true;}
            titleMode=Label(art,"",12,new Vector2(0,0),new Vector2(1,.14f),new Color(.55f,.68f,.71f));
        }
        public void ShowGame(GameView view)
        {
            DismissErrorNotice();
            int previous=confirmed?.state.flags?.Length ?? 0;
            string oldLocation=confirmed?.location.id;bool fresh=confirmed?.session_id!=view.session_id;
            SetFooter(true);
            if(confirmed?.session_id!=view.session_id){scannerEvidence=true;StoryText="";}
            confirmed=view;DiagnosticEvidence=EvidenceText(view,ReplayVerification);
            if(!string.IsNullOrEmpty(view.narrative)&&view.narrative!="Position saved.")StoryText=view.narrative;
            ClearOverlay(); TitleVisible = false; CloseDialogue(); hud.gameObject.SetActive(true);tools.gameObject.SetActive(true);nightClock.gameObject.SetActive(true);
            for(int i=0;i<visitLights.Count;i++)visitLights[i].color=i<view.state.visits ? new Color(.22f,.3f,.4f) : gold;
            if((view.state.flags?.Length ?? 0)>previous)audioCues.Discovery();
            if(oldLocation!=null&&oldLocation!=view.location.id)audioCues.Open();
            location.text=NightArt.Venue(view.location.id);
            modeLabel.text=(ReplayVerification?"REPLAY PREVIEW · ":"")+(12-view.state.visits)+" visits remain";
            var lines = new List<string>();
            int completed=0; foreach(var item in view.objectives)if(item.completed)completed++;
            string localGoal=view.location.id=="quay"?"map":view.location.id=="market"?"rhythm":view.location.id=="archive"?"chronicle":"beacon";
            Objective next=Array.Find(view.objectives,o=>!o.completed&&o.id==localGoal) ?? Array.Find(view.objectives,o=>!o.completed);
            if(view.location.id=="market")next=Array.Find(view.objectives,o=>!o.completed&&o.id.StartsWith("trace_",StringComparison.Ordinal))??next;
            if(view.location.id=="station")next=Array.Find(view.objectives,o=>!o.completed&&o.id.StartsWith("proof_",StringComparison.Ordinal))??next;
            if(view.location.id=="archive")next=Array.Find(view.objectives,o=>!o.completed&&o.id.StartsWith("culture_",StringComparison.Ordinal))??next;
            lines.Add(next!=null ? "NEXT · "+next.label : "Every memory is secured.");

            objectives.text = string.Join("\n", lines);
            if(fresh&&(view.state.cultural_context?.rule_version=="cultural-investigation-v2"||view.state.cultural_context?.rule_version=="cultural-understanding-v3")&&!PlayerPrefs.HasKey("is.learnedInvestigation"))ShowTutorial();
            if (!string.IsNullOrEmpty(view.narrative)&&view.narrative!="Position saved.") Status((view.narrative_source == "game_master_no_state_change" ? "Game Master reflection (no game changes): " : "") + view.narrative);
        }
        public void ShowDialogue(GameView view, WorldObject obj, Action<Command> act)
        {
            CloseDialogue(); Blocking = true; ActivePanel="dialogue"; ActivePanelText=obj.text; SetHudVisible(true); audioCues.Open();
            footer.gameObject.SetActive(false);
            dialogue=Panel(canvas,Vector2.zero,new Vector2(1,.32f),ink);
            if(obj.kind=="npc"||obj.kind=="gate"){
                var portrait=Panel(dialogue,new Vector2(.025f,.51f),new Vector2(.085f,.94f),Color.white).GetComponent<Image>();
                portrait.sprite=NightArt.Character(obj.kind=="gate"?5:view.location.id=="market"?2:view.location.id=="archive"?3:1,1,0);portrait.preserveAspect=true;
            }
            Label(dialogue,obj.name,21,new Vector2(.10f,.82f),new Vector2(.80f,.98f),gold);
            dialogueFeedback=Passage(dialogue,obj.text,new Vector2(.10f,.49f),new Vector2(.96f,.81f));
            float y=.25f;int optionIndex=0;
            if(obj.kind=="portal"){Button(dialogue,"Enter venue",new Vector2(.10f,y),new Vector2(.47f,y+.15f),()=>act(new Command{kind="travel",target=obj.id}));optionIndex++;}
            WorldObject nearby = Array.Find(view.nearby, o => o.id == obj.id);
            foreach (var option in nearby?.choices ?? Array.Empty<StoryChoice>())
            {
                StoryChoice choice = option;
                float left=.10f+optionIndex*.39f;Button(dialogue,choice.label,new Vector2(left,y),new Vector2(left+.37f,y+.15f),()=>act(new Command{kind="choose",target=obj.id,choice=choice.id}));optionIndex++;
            }
            Button(dialogue,"Close",new Vector2(.88f,.83f),new Vector2(.97f,.98f),CloseDialogue);
            actionInput.transform.SetParent(dialogue,false);askButton.transform.SetParent(dialogue,false);
            Place(actionInput.GetComponent<RectTransform>(),new Vector2(.10f,.035f),new Vector2(.80f,.20f));Place(askButton.GetComponent<RectTransform>(),new Vector2(.815f,.035f),new Vector2(.975f,.20f));
        }
        public void CloseDialogue()
        { if (dialogue != null) {
            actionInput.transform.SetParent(footer,false);askButton.transform.SetParent(footer,false);
            Place(actionInput.GetComponent<RectTransform>(),new Vector2(.025f,.08f),new Vector2(.80f,.37f));Place(askButton.GetComponent<RectTransform>(),new Vector2(.815f,.08f),new Vector2(.975f,.37f));
            dialogue.gameObject.SetActive(false); Destroy(dialogue.gameObject); } dialogue = null; if(footer!=null)footer.gameObject.SetActive(!TitleVisible); Blocking = overlay != null; if(!Blocking){ActivePanel="";ActivePanelText="";if(!TitleVisible&&confirmed!=null)SetHudVisible(true);} }
        public void ShowPause()
        {
            ClearOverlay(); CloseDialogue(); Blocking = true;
            overlay = Panel(canvas,new Vector2(.65f,.18f),new Vector2(1,.915f),ink);
            footer.gameObject.SetActive(false);
            ActivePanel="pause";SetHudVisible(false);
            Label(overlay, "A MOMENT OF QUIET", 23, new Vector2(.08f,.8f), new Vector2(.92f,.95f), gold);
            Button(overlay, "Return to the city", new Vector2(.08f,.64f), new Vector2(.92f,.75f), ClearOverlay);
            Button(overlay, "Retry pending request", new Vector2(.08f,.49f), new Vector2(.92f,.60f), () => Retry?.Invoke());
            Button(overlay, "Reload confirmed save", new Vector2(.08f,.34f), new Vector2(.92f,.45f), () => Reload?.Invoke());
            Button(overlay,"Sound",new Vector2(.56f,.19f),new Vector2(.92f,.30f),ToggleSound);
            bool highContrast = PlayerPrefs.GetInt("is.contrast", 0) == 1;
            Button(overlay, "High contrast", new Vector2(.08f,.19f), new Vector2(.54f,.30f), () => {
                highContrast = !highContrast; PlayerPrefs.SetInt("is.contrast", highContrast ? 1 : 0); PlayerPrefs.Save();
                ink = highContrast ? Color.black : new Color(.035f,.065f,.1f,1);
                overlay.GetComponent<Image>().color = ink; });
            Button(overlay, "Save & return to title", new Vector2(.08f,.04f), new Vector2(.92f,.15f), () => ReturnTitle?.Invoke());
        }
        public void ToggleSound(){PlayerPrefs.SetInt("is.muted",PlayerPrefs.GetInt("is.muted",0)==0?1:0);PlayerPrefs.Save();audioCues.RefreshMute();Status(PlayerPrefs.GetInt("is.muted",0)==1?"Sound muted.":"Sound enabled.");}
        public void ShowEnding(GameView view)
        {
            if(tutorial!=null){Destroy(tutorial.gameObject);tutorial=null;}
            ClearOverlay();CloseDialogue();Blocking=true;SetHudVisible(false);ActivePanel="ending";
            overlay=Panel(canvas,new Vector2(.57f,.03f),new Vector2(.98f,.89f),ink);footer.gameObject.SetActive(false);
            string title=view.state.ending=="keeper"?"KEEPER OF THE LAST LIGHT":view.state.ending=="dawn"?"THE CITY WILL WAIT":"THE WAY INTO DAWN";
            Label(overlay,title,25,new Vector2(.06f,.82f),new Vector2(.94f,.96f),view.state.ending=="dawn"?new Color(.55f,.8f,.8f):gold);
            var lines=new List<string>{"TASTE CARD · YOUR NIGHT",view.state.history[view.state.history.Length-1],"",view.state.ending=="dawn"?"Some stories need another night. Nothing you learned was wasted.":view.state.ending=="keeper"?"You chose to leave a light for the next traveler.":"You carried the city's voices into morning.","",StoryTokens(view.state.flags),"",view.state.visits+" / 12 visits · Your confirmed choices shaped this ending."};
            foreach(var link in view.state.cultural_context?.links ?? Array.Empty<CulturalLink>()){
                var target=Array.Find(link.recommendations,e=>e.entity_id==link.selected_id);
                if(target!=null)lines.Add("Saved Qloo connection: "+link.seed.name+" -> "+target.name);
            }
            if(ReplayVerification)lines.Add("Replay preview · historical cultural responses, not live requests.");
            lines.Add(view.state.mode=="cultural"?"Story settings are our fiction; cultural connections are saved provider evidence.":"Original authored journey · no cultural provider evidence.");
            lines.Add("No individual personality profile or taste score was inferred.");
            ScrollBody(overlay,string.Join("\n",lines),.80f,.26f);
            Button(overlay,"Explore saved discoveries",new Vector2(.06f,.14f),new Vector2(.94f,.23f),ShowScanner);
            Button(overlay,"Return to title",new Vector2(.06f,.025f),new Vector2(.94f,.12f),()=>ReturnTitle?.Invoke());
            if(endingCueSession!=view.session_id){endingCueSession=view.session_id;audioCues.Ending(view.state.ending=="dawn");}
        }
        public void ShowTutorial(){
            if(tutorial!=null)Destroy(tutorial.gameObject);
            tutorial=Panel(canvas,new Vector2(.025f,.66f),new Vector2(.40f,.90f),ink);
            Label(tutorial,"YOUR FIRST NIGHT",18,new Vector2(.05f,.77f),new Vector2(.92f,.97f),gold);
            Label(tutorial,"WASD / arrows · E to investigate\nA new conversation spends one visit.\nContinuing it is free; leave the last one before dawn only if ready.\nMara / Ivo's notes / Sera / Curator\nC: Scanner · J: Journal · Esc: close/menu",15,new Vector2(.05f,.20f),new Vector2(.95f,.77f),pale);
            Button(tutorial,"Understood",new Vector2(.05f,.025f),new Vector2(.95f,.20f),()=>{PlayerPrefs.SetInt("is.learnedInvestigation",1);PlayerPrefs.Save();Destroy(tutorial.gameObject);tutorial=null;});
        }
        public void ShowStory(){if(confirmed==null||TitleVisible)return;OpenNotebook("STORY SO FAR","story");ScrollBody(overlay,string.IsNullOrEmpty(StoryText)?string.Join("\n",confirmed.state.history):StoryText);}
        void SetFooter(bool game){if(footer==null)return;footer.gameObject.SetActive(game);actionInput.gameObject.SetActive(game);askButton.gameObject.SetActive(game);}
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
                    default:labels.Add(flag.StartsWith("trace_",StringComparison.Ordinal)?"Screening clue":flag.StartsWith("proof_",StringComparison.Ordinal)?"Verified affinity":flag.StartsWith("culture_",StringComparison.Ordinal)?"Cultural memory":flag.Replace('_',' '));break;
                }
            }
            return labels.Count==0 ? "No story tokens collected yet." : string.Join(" · ",labels);
        }
        public void SetScannerTool(string name){int index=Array.IndexOf(new[]{"search","related","inspect","progress","record"},name);if(index>=0){scannerTool=index;ShowScanner();}}
        public void ShowScanner()
        {
            if(confirmed==null||TitleVisible)return;
            OpenNotebook("CULTURAL SCANNER","scanner");
            string[] names={"Search","Related","Inspect","Progress","Record"};
            for(int i=0;i<5;i++){int tool=i;float x=.04f+i*.185f;Button(overlay,names[i],new Vector2(x,.81f),new Vector2(x+.177f,.88f),()=>{scannerTool=tool;ShowScanner();});}
            var query=Input(overlay,"Search this run's saved catalogue",new Vector2(.05f,.70f),new Vector2(.95f,.78f));query.text=scannerQuery;
            scannerBodyText=CreateScannerBody(ScannerText(confirmed,scannerTool,scannerQuery,ReplayVerification,scannerEvidence));
            query.onValueChanged.AddListener(text=>{scannerQuery=text;string body=ScannerText(confirmed,scannerTool,text,ReplayVerification,scannerEvidence);scannerBodyText.text=body;ActivePanelText=body;});
            if(scannerTool==4){
                StoryChoice record=null;WorldObject target=null;
                foreach(var obj in confirmed.nearby)foreach(var option in obj.choices??Array.Empty<StoryChoice>())if(option.id.StartsWith("trace_",StringComparison.Ordinal)||option.id.StartsWith("echo_",StringComparison.Ordinal)||option.id.StartsWith("prove_",StringComparison.Ordinal)){target=obj;record=option;break;}
                if(record!=null){var chosen=record;var obj=target;Button(overlay,"Record nearby discovery",new Vector2(.05f,.12f),new Vector2(.70f,.20f),()=>RecordDiscovery?.Invoke(new Command{kind="choose",target=obj.id,choice=chosen.id}));}
            }else Button(overlay,scannerEvidence?"Qloo off: authored control":"Return to saved evidence",new Vector2(.05f,.12f),new Vector2(.70f,.20f),ToggleScannerComparison);
            Label(overlay,"Saved catalogue · no new provider requests",12,new Vector2(.05f,.04f),new Vector2(.73f,.10f),pale);
        }
        Text CreateScannerBody(string body){ScrollBody(overlay,body,.68f,.23f);return overlay.GetChild(overlay.childCount-1).GetComponentInChildren<Text>();}
        public static string ScannerText(GameView view,int tool,string query,bool replay,bool evidence=true){
            if(!evidence)return EvidenceText(view,replay,false,false);
            var lines=new List<string>{replay?"REPLAY EVIDENCE · captured cultural results":"SAVED QLOO EVIDENCE","No new live search. Affinity is not identity or collaboration.",""};
            var links=view.state.cultural_context?.links??Array.Empty<CulturalLink>();
            if(links.Length==0)return "This authored journey has no cultural catalogue. Start a cultural run to investigate actual saved recommendations.";
            for(int i=0;i<links.Length;i++){
                var link=links[i];var selected=Array.Find(link.recommendations,e=>e.entity_id==link.selected_id);
                if(tool==0){foreach(var item in new[]{link.seed})if(string.IsNullOrEmpty(query)||item.name.IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0)lines.Add(item.name+" ["+item.category+"] · resolved seed");foreach(var item in link.recommendations)if(string.IsNullOrEmpty(query)||item.name.IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0)lines.Add(item.name+" ["+item.category+"] · returned result");}
                else if(tool==1){lines.Add(link.seed.name+" -> "+string.Join(" · ",Array.ConvertAll(link.recommendations,e=>e.name)));}
                else if(tool==3||tool==4){lines.Add(link.seed.name+" -> "+selected.name);foreach(var stage in (view.state.cultural_context.rule_version=="cultural-investigation-v2"||view.state.cultural_context.rule_version=="cultural-understanding-v3")?new[]{"trace_","culture_","proof_"}:new[]{"culture_"})lines.Add((Array.IndexOf(view.state.flags,stage+i)>=0?"CONFIRMED · ":"MISSING · ")+(stage=="trace_"?"Ivo's screening note":stage=="culture_"?"Sera's memory card":"Curator's supported claim"));lines.Add("Our creative setting: "+link.setting+" (fiction).\n");}
            }
            if(tool==2)return EvidenceText(view,replay,true,true).Replace("LOCAL CAPTURE REPLAY","REPLAY EVIDENCE");
            if(tool==4)lines.Add("Approach a screening note, memory card or the Curator. Record uses only the currently allowed server choice. Starting a resident or Curator encounter spends one visit.");
            if(tool==0&&lines.Count==3)lines.Add("No saved entity matches. Change the query; new cultural favourites require a new run.");
            return string.Join("\n",lines);
        }
        public void ToggleScannerComparison(){if(ActivePanel=="scanner"){scannerEvidence=!scannerEvidence;ShowScanner();}}
        // Pure presentation of server-confirmed data. No inference or synthetic provider facts.
        public string DiagnosticEvidence {get;private set;}="";
        public static string EvidenceText(GameView view,bool replay,bool evidence=true,bool diagnostics=true)
        {
            if(!evidence)return "QLOO OFF · AUTHORED CONTROL\nInvented setting, not cultural evidence.\n\nA quiet night city. Three residents offer a way home, a rhythm and a promise.\n\nThis comparison changes only this panel. Your real saved cultural context, quest and progress remain unchanged.";
            var lines=new List<string>{replay?(diagnostics?"LOCAL CAPTURE REPLAY · historical Qloo responses, no live calls":"REPLAY PREVIEW · saved Qloo responses, no live requests"):"SAVED QLOO EVIDENCE · no new requests", "Recommendations express aggregate cultural affinity, not facts about your personality or a collaboration.",""};
            var links=view?.state?.cultural_context?.links;
            if(links==null || links.Length==0) {lines.Add("Authored chapter · no Qloo cultural evidence is attached to this save.");return string.Join("\n",lines);}
            foreach(var link in links) {
                lines.Add("SEED · "+link.seed.name+" ["+link.seed.category+"]");if(diagnostics)lines.Add("Entity: "+link.seed.entity_id);
                foreach(var item in link.recommendations ?? Array.Empty<CulturalEntity>()) {
                    lines.Add("\n"+(item.entity_id==link.selected_id?"SELECTED · ":"RELATED · ")+item.name+" ["+item.category+"]"+(item.year>0?" · "+item.year:""));

                    if(diagnostics)lines.Add("Entity: "+item.entity_id);
                    if(!string.IsNullOrEmpty(item.description))lines.Add(item.description);
                    var tags=new List<string>();foreach(var tag in item.tags ?? Array.Empty<CulturalTag>())tags.Add(tag.name);if(tags.Count>0)lines.Add("Qloo tags: "+string.Join(" · ",tags));
                }
                lines.Add("\nOUR CREATIVE SETTING · "+link.setting+" (fictional interpretation; not a Qloo fact)");
                foreach(var proof in link.evidence ?? Array.Empty<CulturalEvidence>()) lines.Add(diagnostics?"Provenance · "+proof.origin+proof.path+"\nRetrieved "+proof.retrieved_at+" · SHA256 "+proof.body_sha256:"Source · Qloo · retrieved "+proof.retrieved_at);
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
            if(confirmed.state.cultural_context!=null){lines.Add("\nRELATIONSHIP BOARD · saved evidence");lines.Add(ScannerText(confirmed,3,"",ReplayVerification));}
            lines.Add("\nINVENTORY / STORY TOKENS (fictional)");lines.Add(StoryTokens(confirmed.state.flags));
            lines.Add("\nCONFIRMED JOURNEY");foreach(var entry in confirmed.state.history ?? Array.Empty<string>())lines.Add("• "+entry+"\n");
            lines.Add("\nART & SOUND · Kenney (CC0) · original night composition by Infinite Stories.");ScrollBody(overlay,string.Join("\n",lines));Button(overlay,"Latest conversation",new Vector2(.05f,.12f),new Vector2(.56f,.20f),ShowStory);Button(overlay,"Help",new Vector2(.60f,.12f),new Vector2(.92f,.20f),ShowTutorial);
        }
        void OpenNotebook(string title,string kind)
        {
            ClearOverlay();CloseDialogue();Blocking=true;ActivePanel=kind;SetHudVisible(true);audioCues.Open();
            overlay=Panel(canvas,new Vector2(.60f,.02f),new Vector2(1,.915f),ink);footer.gameObject.SetActive(false);
            Label(overlay,title,27,new Vector2(.05f,.90f),new Vector2(.92f,.98f),gold);
            Button(overlay,"Close",new Vector2(.76f,.025f),new Vector2(.95f,.085f),()=>{if(!string.IsNullOrEmpty(confirmed?.state.ending))ShowEnding(confirmed);else ClearOverlay();});
        }
        void SetHudVisible(bool visible){hud.gameObject.SetActive(visible);tools.gameObject.SetActive(visible);nightClock.gameObject.SetActive(visible);if(visible&&!TitleVisible&&overlay==null&&dialogue==null)footer.gameObject.SetActive(true);}
        void ScrollBody(RectTransform parent,string body,float top=.85f,float bottom=.23f)
        {
            ActivePanelText=body;
            Passage(parent,body,new Vector2(.05f,bottom),new Vector2(.95f,top));
        }
        Text Passage(Transform parent,string body,Vector2 min,Vector2 max){
            var viewport=Panel(parent,min,max,new Color(.025f,.05f,.08f));
            viewport.gameObject.AddComponent<RectMask2D>();
            var content=Label(viewport,body,17,Vector2.zero,Vector2.one,pale);
            var rect=content.rectTransform;rect.anchorMin=new Vector2(0,1);rect.anchorMax=Vector2.one;rect.pivot=new Vector2(.5f,1);rect.offsetMin=new Vector2(12,0);rect.offsetMax=new Vector2(-18,0);
            var fitter=content.gameObject.AddComponent<ContentSizeFitter>();fitter.verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            var scroll=viewport.gameObject.AddComponent<ScrollRect>();scroll.viewport=viewport;scroll.content=rect;scroll.horizontal=false;scroll.movementType=ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=28;return content;
            // The viewport catches wheel/drag; text itself remains non-interactive.
        }
        RectTransform Panel(Transform parent, Vector2 min, Vector2 max, Color color)
        { var go = new GameObject("Panel", typeof(RectTransform), typeof(Image)); go.transform.SetParent(parent, false); var rect = go.GetComponent<RectTransform>(); Place(rect,min,max); go.GetComponent<Image>().color = color; if(parent==canvas){var reveal=go.AddComponent<PanelReveal>();reveal.Duration=.16f;} return rect; }
        Text Label(Transform parent, string value, int size, Vector2 min, Vector2 max, Color color)
        { var go = new GameObject("Text", typeof(RectTransform), typeof(Text)); go.transform.SetParent(parent,false); var text = go.GetComponent<Text>(); Place(go.GetComponent<RectTransform>(),min,max); text.font=font; text.fontSize=size; text.color=color; text.text=value; text.supportRichText=false; text.horizontalOverflow=HorizontalWrapMode.Wrap; text.verticalOverflow=VerticalWrapMode.Truncate; text.raycastTarget=false; return text; }
        Button Button(Transform parent, string label, Vector2 min, Vector2 max, Action click)
        { var rect=Panel(parent,min,max,new Color(.12f,.23f,.29f)); var button=rect.gameObject.AddComponent<Button>(); button.targetGraphic=rect.GetComponent<Image>(); button.onClick.AddListener(() => { audioCues?.Click(); click(); }); var text=Label(rect,label,17,new Vector2(.04f,.08f),new Vector2(.96f,.92f),pale); text.alignment=TextAnchor.MiddleCenter;text.resizeTextForBestFit=true;text.resizeTextMinSize=13;text.resizeTextMaxSize=17; return button; }
        InputField Input(Transform parent, string placeholder, Vector2 min, Vector2 max)
        { var rect=Panel(parent,min,max,new Color(.09f,.14f,.2f)); var field=rect.gameObject.AddComponent<InputField>(); field.targetGraphic=rect.GetComponent<Image>(); field.characterLimit=1000; field.textComponent=Label(rect,"",17,new Vector2(.03f,.08f),new Vector2(.97f,.92f),pale); var hint=Label(rect,placeholder,16,new Vector2(.03f,.08f),new Vector2(.97f,.92f),new Color(.5f,.65f,.7f)); field.placeholder=hint; return field; }
        static void Place(RectTransform rect, Vector2 min, Vector2 max) { rect.anchorMin=min; rect.anchorMax=max; rect.offsetMin=Vector2.zero; rect.offsetMax=Vector2.zero; }
    }
}
