using System.Collections.Generic;
using UnityEngine;

namespace InfiniteStories
{
    // Imported Kenney CC0 sprites; indices are checked against the downloaded 16px tiles.
    public static class NightArt
    {
        static readonly Dictionary<int,Sprite> tiles=new Dictionary<int,Sprite>();
        public static Sprite Tile(int id) {
            if (!tiles.TryGetValue(id,out var sprite)) { sprite=Resources.Load<Sprite>("Art/Urban/tile_"+id.ToString("D4")); tiles[id]=sprite; }
            return sprite;
        }
        public static bool IsCharacter(int id) {
            for(int actor=0;actor<6;actor++) for(int frame=0;frame<3;frame++)
                if(id>=23+actor*81+frame*27 && id<27+actor*81+frame*27) return true;
            return false;
        }
        // Direction order in source: west, south, north, east. Frame0 is standing.
        public static Sprite Character(int actor,int direction,int frame) => Tile(23+Mathf.Clamp(actor,0,5)*81+Mathf.Clamp(frame,0,2)*27+Mathf.Clamp(direction,0,3));
        public static string Venue(string id) => id=="quay" ? "SIDE A · RECORD BAR" : id=="market" ? "AFTERIMAGE · CINEMA" : id=="archive" ? "THREAD & ECHO · BOUTIQUE" : id=="station" ? "THE LAST GATE" : "NIGHT CITY";
        public static Color Accent(string id) => id=="market" ? new Color(.9f,.47f,.55f) : id=="archive" ? new Color(.54f,.76f,.72f) : new Color(.96f,.73f,.42f);
    }
    public sealed class CityCharacter : MonoBehaviour
    {
        static readonly int[] walk={0,1,0,2};
        public int Actor; public int Facing=1;
        SpriteRenderer visual,animated; bool walking; float talkingUntil;
        public void Emphasize(){talkingUntil=Time.unscaledTime+1.4f;}
        public void Pose(Vector2 direction,bool moving) {
            if(visual==null) visual=GetComponent<SpriteRenderer>();
            walking=moving;
            if(direction.sqrMagnitude>.01f) Facing=Mathf.Abs(direction.x)>Mathf.Abs(direction.y) ? (direction.x<0?0:3) : (direction.y<0?1:2);
            int frame=walking?walk[(int)(Time.unscaledTime*7)%4]:0;
            visual.sprite=NightArt.Character(Actor,Facing,frame);visual.flipX=false;
        }
        void LateUpdate() {
            if(visual==null)visual=GetComponent<SpriteRenderer>();
            if(animated==null){var go=new GameObject("Animated silhouette");go.transform.SetParent(transform,false);animated=go.AddComponent<SpriteRenderer>();visual.enabled=false;}
            visual.sortingOrder=400-Mathf.RoundToInt(transform.position.y*10);
            animated.sprite=visual.sprite;animated.sortingOrder=visual.sortingOrder;animated.color=visual.color;
            float breath=Mathf.Sin(Time.unscaledTime*(walking?14:2)+Actor);
            animated.transform.localPosition=new Vector3(0,walking?Mathf.Abs(breath)*.035f:.012f*breath,0);
            animated.transform.localScale=new Vector3(1,1+(walking ? .015f : .007f)*breath,1);
            if(Time.unscaledTime<talkingUntil)animated.color=Color.Lerp(visual.color,new Color(1,.86f,.64f),.18f);
        }
    }
    public sealed class NightPulse : MonoBehaviour
    {
        SpriteRenderer visual; Color color;
        void Start(){ visual=GetComponent<SpriteRenderer>(); color=visual.color; }
        void Update(){var c=color;c.a*=.86f+.14f*Mathf.Sin(Time.unscaledTime*1.7f+transform.position.x);visual.color=c;}
    }
    public sealed class NightRain : MonoBehaviour
    {
        readonly List<Transform> drops=new List<Transform>(); Sprite sprite;
        void Start(){sprite=OriginalArt.Solid(Color.white);for(int i=0;i<36;i++){var go=new GameObject("Rain");go.transform.SetParent(transform);go.transform.position=new Vector3(1+(i*17%300)/10f,1+(i*37%150)/10f,0);go.transform.localScale=new Vector3(.025f,.22f,1);var r=go.AddComponent<SpriteRenderer>();r.sprite=sprite;r.color=new Color(.55f,.73f,.83f,.15f);r.sortingOrder=450;drops.Add(go.transform);}}
        void Update(){foreach(var drop in drops){drop.position+=new Vector3(-.6f,-5,0)*Time.deltaTime;if(drop.position.y<.8f)drop.position=new Vector3(drop.position.x<1?30:drop.position.x,16,0);}}
        void OnDestroy(){if(sprite!=null){Destroy(sprite.texture);Destroy(sprite);}}
    }
    public sealed class PanelReveal : MonoBehaviour
    {
        public float Duration=.16f; CanvasGroup group; float started;
        void Awake(){group=gameObject.AddComponent<CanvasGroup>();group.alpha=0;started=Time.unscaledTime;}
        void Update(){group.alpha=Mathf.Clamp01((Time.unscaledTime-started)/Duration);if(group.alpha>=1)enabled=false;}
    }
    public sealed class CityAudio : MonoBehaviour
    {
        AudioSource source,ambient; AudioClip click,open,discovery,foot,bed; bool activated;
        public void Initialize(){
            source=gameObject.AddComponent<AudioSource>();source.playOnAwake=false;source.volume=.16f;
            click=Resources.Load<AudioClip>("Art/Audio/click_001");open=Resources.Load<AudioClip>("Art/Audio/open_001");discovery=Resources.Load<AudioClip>("Art/Audio/confirmation_001");
            ambient=gameObject.AddComponent<AudioSource>();ambient.playOnAwake=false;ambient.loop=true;ambient.volume=.025f;
            const int hz=22050;var noise=new System.Random(42);var samples=new float[hz*2];float filtered=0;
            for(int i=0;i<samples.Length;i++){filtered=filtered*.96f+((float)noise.NextDouble()*2-1)*.04f;float edge=Mathf.Min(1,Mathf.Min(i,samples.Length-1-i)/1000f);samples[i]=filtered*edge;}
            bed=AudioClip.Create("Original night air",samples.Length,1,hz,false);bed.SetData(samples,0);ambient.clip=bed;
            samples=new float[700];for(int i=0;i<samples.Length;i++)samples[i]=((float)noise.NextDouble()*2-1)*Mathf.Exp(-i/90f)*.2f;
            foot=AudioClip.Create("Original soft footfall",samples.Length,1,hz,false);foot.SetData(samples,0);
        }
        public void Activate(){activated=true;RefreshMute();}
        public void RefreshMute(){if(ambient==null)return;if(activated&&PlayerPrefs.GetInt("is.muted",0)==0){if(!ambient.isPlaying)ambient.Play();}else ambient.Stop();}
        void Play(AudioClip clip,float volume=1){if(source!=null&&clip!=null&&PlayerPrefs.GetInt("is.muted",0)==0){Activate();source.PlayOneShot(clip,volume);}}
        public void Click(){Play(click);}
        public void Open(){Play(open);}
        public void Discovery(){Play(discovery);}
        public void Step(){Play(foot,.18f);}
        public void Ending(bool gentle){Play(gentle?open:discovery,.7f);}
        void OnDestroy(){if(foot!=null)Destroy(foot);if(bed!=null)Destroy(bed);}
    }
}
