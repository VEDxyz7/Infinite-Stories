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
        public int Actor;
        public int Facing=1;
        SpriteRenderer visual;
        public void Pose(Vector2 direction,bool walking) {
            if(visual==null) visual=GetComponent<SpriteRenderer>();
            if(direction.sqrMagnitude>.01f) Facing=Mathf.Abs(direction.x)>Mathf.Abs(direction.y) ? (direction.x<0?0:3) : (direction.y<0?1:2);
            int frame=walking ? new[]{0,1,0,2}[(int)(Time.unscaledTime*7)%4] : 0;
            visual.sprite=NightArt.Character(Actor,Facing,frame); visual.flipX=false;
        }
        void LateUpdate() {
            if(visual==null)visual=GetComponent<SpriteRenderer>();
            visual.sortingOrder=400-Mathf.RoundToInt(transform.position.y*10);
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
    public sealed class CityAudio : MonoBehaviour
    {
        AudioSource source; AudioClip click,open,discovery;
        public void Initialize(){source=gameObject.AddComponent<AudioSource>();source.playOnAwake=false;source.volume=.16f;click=Resources.Load<AudioClip>("Art/Audio/click_001");open=Resources.Load<AudioClip>("Art/Audio/open_001");discovery=Resources.Load<AudioClip>("Art/Audio/confirmation_001");}
        public void Click(){if(source!=null&&click!=null&&PlayerPrefs.GetInt("is.muted",0)==0)source.PlayOneShot(click);}
        public void Open(){if(source!=null&&open!=null&&PlayerPrefs.GetInt("is.muted",0)==0)source.PlayOneShot(open);}
        public void Discovery(){if(source!=null&&discovery!=null&&PlayerPrefs.GetInt("is.muted",0)==0)source.PlayOneShot(discovery);}
    }
}
