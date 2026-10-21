using System.Collections.Generic;
using UnityEngine;

namespace InfiniteStories
{
    // Furniture stands only on existing authoritative solid cells. Suspended signs,
    // screens and floor inlays are intentionally nonblocking; no new collision map.
    public sealed class VenueFurniture : MonoBehaviour
    {
        readonly List<Object> owned=new List<Object>();
        readonly List<SpriteRenderer> sockets=new List<SpriteRenderer>();
        Location location;
        public void Build(Location value)
        {
            location=value; Color accent=NightArt.Accent(value.id);
            string[] kinds=value.id=="quay"?new[]{"speaker","crate","turntable","speaker"}:
                value.id=="market"?new[]{"seat","seat","projector","seat"}:
                value.id=="archive"?new[]{"shelf","garment","garment","shelf"}:new[]{"pillar","socket","socket","pillar"};
            for(int y=11;y<=14;y++)for(int x=7;x<=10;x++)
                if(IsSolid(value,x,y)) {
                    string kind=y==11?kinds[x-7]:y==12?(value.id=="quay"?"crate":value.id=="market"?"seat":value.id=="archive"?"shelf":"pillar"):"counter";
                    var r=Place(kind,x,y,accent);r.sortingOrder=400-y*10;
                    r.gameObject.AddComponent<FurnitureFootprint>().Cell=new Vector2Int(x,y);
                }
            for(int x=12;x<=25;x+=3)if(IsSolid(value,x,17)) {
                var r=Place(value.id=="archive"?"garment":value.id=="market"?"poster":"shelf",x,17,accent);r.sortingOrder=230;
                r.gameObject.AddComponent<FurnitureFootprint>().Cell=new Vector2Int(x,17);
            }
            // Versioned server solids carry the additional venue-specific furniture.
            for(int y=9;y<=14;y++)for(int x=5;x<=26;x++)if(IsSolid(value,x,y)&&!(x>=7&&x<=10&&y>=11&&y<=14)){
                string kind=value.id=="market"?"seat":value.id=="archive"?"garment":value.id=="station"?"pillar":"turntable";
                var piece=Place(kind,x,y,accent);piece.sortingOrder=400-y*10;piece.gameObject.AddComponent<FurnitureFootprint>().Cell=new Vector2Int(x,y);
            }
            // Open-front cutaway rooms keep a clear approach from the street.
            if(value.id=="market") {var screen=Place("screen",18,13.5f,accent);screen.transform.localScale=new Vector3(4,2,1);screen.sortingOrder=3;Caption("TONIGHT · THE LAST REEL",18,12.8f);}
            if(value.id=="quay") {Caption("LISTENING ROOM",18,13.6f);for(int x=16;x<=21;x++)Place("record",x,14.3f,accent).sortingOrder=3;}
            if(value.id=="archive") {Caption("WEAR A STORY · KEEP A PROMISE",18,13.6f);for(int x=16;x<=21;x+=2)Place("garment",x,14.5f,accent).sortingOrder=3;}
            if(value.id=="station") {
                Caption("A WAY HOME     A RHYTHM     A PROMISE",14,13.2f);
                for(int i=0;i<3;i++){var s=Place("socket",12+i*2,11,accent);s.transform.localScale=Vector3.one*1.2f;s.sortingOrder=3;sockets.Add(s);}
                for(int x=12;x<=16;x++)Place("threshold",x,7,new Color(.85f,.67f,.4f)).sortingOrder=3;
            }
        }
        public static bool IsSolid(Location place,int x,int y)=>x>=0&&y>=0&&x<place.width&&y<place.height&&place.rows[y][x]=='1';
        public void Confirm(GameState state) {
            string[] flags={"map","rhythm","chronicle"};
            for(int i=0;i<sockets.Count;i++)sockets[i].color=System.Array.IndexOf(state.flags,flags[i])>=0 ? new Color(1,.79f,.4f):new Color(.22f,.30f,.40f);
        }
        SpriteRenderer Place(string kind,float x,float y,Color accent)
        {
            var go=new GameObject("Furnishing · "+kind);go.transform.SetParent(transform);go.transform.position=new Vector3(x,y,0);
            var r=go.AddComponent<SpriteRenderer>();r.sprite=Glyph(kind,accent);r.sortingOrder=4;return r;
        }
        Sprite Glyph(string kind,Color accent)
        {
            // Original pixel furniture, using the imported pack's grid and restrained palette.
            const int n=16;var t=new Texture2D(n,n,TextureFormat.RGBA32,false);t.filterMode=FilterMode.Point;
            Color dark=new Color(.055f,.075f,.12f),wood=new Color(.31f,.21f,.20f),edge=new Color(.47f,.34f,.27f);
            var p=new Color[n*n];
            for(int y=0;y<n;y++)for(int x=0;x<n;x++) {
                bool box=x>0&&x<15&&y>1&&y<14; Color c=Color.clear;
                if(kind=="counter"&&box)c=y>10?edge:wood;
                if(kind=="crate"&&box){c=wood;if(y>5&&x>2&&x<13)c=(x%3==0?accent:dark);if(y==3||x==2||x==13)c=edge;}
                if(kind=="shelf"&&box){c=wood;if(y%5==0)c=edge;else if(x>2&&x<13)c=x%3==0?accent:dark;}
                if(kind=="turntable"&&box){c=wood;float d=Vector2.Distance(new Vector2(x,y),new Vector2(6,8));if(d<5)c=d<1.5f?accent:dark;if(x==12&&y>5)c=accent;}
                if(kind=="record"&&Vector2.Distance(new Vector2(x,y),new Vector2(7.5f,7.5f))<7)c=Vector2.Distance(new Vector2(x,y),new Vector2(7.5f,7.5f))<2?accent:dark;
                if(kind=="speaker"&&box){c=dark;if(x==2||x==13||y==3||y==12)c=edge;if(Vector2.Distance(new Vector2(x,y),new Vector2(8,7))<4)c=new Color(.18f,.22f,.28f);}
                if(kind=="seat"&&x>2&&x<14&&y>1&&y<14)c=y>5?(y==6||x==3||x==13?accent:accent*.55f):dark;
                if(kind=="projector"&&box){c=dark;if(y>8&&(Vector2.Distance(new Vector2(x,y),new Vector2(4,11))<3||Vector2.Distance(new Vector2(x,y),new Vector2(11,11))<3))c=edge;if(x>11&&y>4&&y<8)c=accent;}
                if((kind=="screen"||kind=="poster")&&box)c=x<3||x>12||y<4||y>11?dark:(kind=="screen"?new Color(.65f,.78f,.78f):accent);
                if(kind=="screen"&&x>6&&x<11&&y>5&&y<11)c=new Color(.35f,.5f,.53f);
                if(kind=="garment"){if(y==13&&x>1&&x<15)c=edge;if(y>2&&y<12&&Mathf.Abs(x-7.5f)<(y>8?6:3))c=y%4==0?accent*.75f:accent;}
                if(kind=="pillar"&&x>3&&x<12)c=x==4||x==11?edge:dark;
                if(kind=="socket"){float d=Vector2.Distance(new Vector2(x,y),new Vector2(7.5f,7.5f));if(d<7)c=d>4?accent:dark;}
                if(kind=="threshold"&&(y==7||y==8))c=accent;
                if(c.a>0)c.a=1;p[y*n+x]=c;
            }
            t.SetPixels(p);t.Apply();var s=Sprite.Create(t,new Rect(0,0,n,n),new Vector2(.5f,.5f),16);owned.Add(t);owned.Add(s);return s;
        }
        void Caption(string text,float x,float y){var t=new GameObject("Interior caption").AddComponent<TextMesh>();t.transform.SetParent(transform);t.transform.position=new Vector3(x,y,0);t.text=text;t.fontSize=48;t.characterSize=.065f;t.anchor=TextAnchor.MiddleCenter;t.color=NightArt.Accent(location.id);t.GetComponent<MeshRenderer>().sortingOrder=20;}
        void OnDestroy(){foreach(var item in owned)if(item!=null)Destroy(item);}
    }
    public sealed class FurnitureFootprint : MonoBehaviour { public Vector2Int Cell; }
}
