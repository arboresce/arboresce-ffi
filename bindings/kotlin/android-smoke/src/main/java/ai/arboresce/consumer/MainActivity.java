package ai.arboresce.consumer;
import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import ai.arboresce.Arboresce;
public class MainActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        for (int i = 0; i < 10000; i++) {
            if (!Arboresce.name().equals("Arboresce")) throw new AssertionError("name");
        }
        Arboresce.printName();
        Log.i("ArboresceConsumer", "ARBORESCE_CONSUMER_OK");
        finish();
    }
}
